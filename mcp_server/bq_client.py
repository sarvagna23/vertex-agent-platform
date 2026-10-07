"""Shared BigQuery helpers. Used by the MCP server and by the eval scripts, so both hit the same code path."""
import json
import re
from functools import lru_cache

import config

# Keywords that must never appear in an analyst query. This is defense in depth only.
# The real safety net is IAM (dataViewer + jobUser) and the maximum_bytes_billed cap.
FORBIDDEN_KEYWORDS = re.compile(
    r"\b(insert|update|delete|merge|drop|create|alter|truncate|grant|revoke|call|export|load|execute|assert)\b",
    re.IGNORECASE,
)
STRING_LITERAL = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
LINE_COMMENT = re.compile(r"--[^\n]*")


@lru_cache(maxsize=1)
def get_client():
    """Create one BigQuery client per process. Imported lazily so unit tests need no GCP libraries."""
    from google.cloud import bigquery

    return bigquery.Client(project=config.PROJECT_ID, location=config.BQ_LOCATION)


def validate_readonly_sql(sql: str) -> str:
    """Return the cleaned query, or raise ValueError if it is not a single read-only SELECT.

    Steps: strip comments and string literals (so words inside text do not trigger the
    keyword check), require one statement, require SELECT or WITH, reject write keywords.
    """
    no_comments = LINE_COMMENT.sub(" ", BLOCK_COMMENT.sub(" ", sql))
    cleaned = no_comments.strip().rstrip(";").strip()
    if not cleaned:
        raise ValueError("Empty SQL.")

    skeleton = STRING_LITERAL.sub("''", cleaned)  # literals blanked out, structure kept
    if ";" in skeleton:
        raise ValueError("Only a single statement is allowed.")

    first_word = skeleton.split(None, 1)[0].lower()
    if first_word not in ("select", "with"):
        raise ValueError("Only SELECT queries are allowed.")

    forbidden_match = FORBIDDEN_KEYWORDS.search(skeleton)
    if forbidden_match:
        raise ValueError(f"Query contains a forbidden keyword: {forbidden_match.group(0)}")

    return cleaned


def _json_safe(rows: list[dict]) -> list[dict]:
    """BigQuery returns dates, decimals and similar types. Round trip through JSON to make them plain."""
    return json.loads(json.dumps(rows, default=str))


def vector_search(query_text: str, top_k: int = 5) -> list[dict]:
    """Semantic search over complaint narratives.

    BigQuery embeds the query with the same remote model used for the table, then
    VECTOR_SEARCH returns the top_k nearest rows by cosine distance (smaller is closer).
    """
    top_k = max(1, min(int(top_k), 20))  # clamp, and it is an int so safe to inline
    embeddings_table = config.fq(config.EMBEDDINGS_TABLE)
    model = config.fq(config.EMBEDDING_MODEL)

    sql = f"""
    SELECT
      base.complaint_id AS complaint_id,
      base.product AS product,
      base.issue AS issue,
      SUBSTR(base.narrative, 1, 600) AS narrative_excerpt,
      distance
    FROM VECTOR_SEARCH(
      TABLE `{embeddings_table}`,
      'embedding',
      (
        SELECT ml_generate_embedding_result AS embedding
        FROM ML.GENERATE_EMBEDDING(
          MODEL `{model}`,
          (SELECT @query_text AS content),
          STRUCT(TRUE AS flatten_json_output)
        )
      ),
      top_k => {top_k},
      distance_type => 'COSINE'
    )
    ORDER BY distance
    """

    from google.cloud import bigquery

    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("query_text", "STRING", query_text)],
        maximum_bytes_billed=config.MAX_BYTES_BILLED,
    )
    result_rows = get_client().query(sql, job_config=job_config).result()
    return _json_safe([dict(row) for row in result_rows])


def run_readonly_sql(sql: str, max_rows: int | None = None) -> dict:
    """Run a validated SELECT with a billing cap and a row cap, and return rows plus metadata."""
    from google.cloud import bigquery

    max_rows = min(max_rows or config.MAX_SQL_ROWS, config.MAX_SQL_ROWS)
    cleaned_sql = validate_readonly_sql(sql)

    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=config.MAX_BYTES_BILLED)
    query_job = get_client().query(cleaned_sql, job_config=job_config)
    result = query_job.result(max_results=max_rows)

    rows = _json_safe([dict(row) for row in result])
    return {
        "rows": rows,
        "returned_rows": len(rows),
        "total_rows": result.total_rows,
        "truncated": bool(result.total_rows and result.total_rows > len(rows)),
    }
