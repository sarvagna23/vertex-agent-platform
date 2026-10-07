"""MCP server that exposes BigQuery to the agents as three tools.

Run standalone to test:   python -m mcp_server.server
The ADK agents launch it themselves as a subprocess over stdio, so you rarely run it by hand.
"""
import config
from mcp_server import bq_client

try:  # mcp 2.x renamed FastMCP to MCPServer, the decorator and run() are the same
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

mcp = _Server("bigquery-complaints")

SCHEMA_TEXT = f"""
Dataset: {config.PROJECT_ID}.{config.BQ_DATASET}  (BigQuery standard SQL, always use fully qualified names with backticks)

Table `{config.fq(config.RAW_TABLE)}` : one row per CFPB consumer complaint
  complaint_id STRING, date_received DATE, product STRING, subproduct STRING,
  issue STRING, subissue STRING, narrative STRING, company_name STRING, state STRING,
  company_response_to_consumer STRING, timely_response BOOL

Table `{config.fq(config.EMBEDDINGS_TABLE)}` : complaint_id, product, issue, narrative, embedding (vector).
  Do not select the embedding column. Use the vector_search_complaints tool for semantic search.
"""


@mcp.tool()
def describe_schema() -> str:
    """Return the table schemas the analyst can query. Call this once before writing SQL."""
    return SCHEMA_TEXT


@mcp.tool()
def vector_search_complaints(query: str, top_k: int = 5) -> dict:
    """Find complaints semantically similar to the query text.

    Returns the closest complaints with product, issue, a narrative excerpt and a cosine
    distance (smaller means more similar). top_k is capped at 20.
    """
    try:
        return {"results": bq_client.vector_search(query, top_k)}
    except Exception as error:  # return the error so the agent can react instead of crashing the run
        return {"error": f"vector search failed: {error}"}


@mcp.tool()
def run_sql(sql: str) -> dict:
    """Run one read-only BigQuery SELECT and return the rows.

    Rules enforced by the server: single SELECT or WITH statement, no writes, row cap,
    and a bytes-billed cap. If the query is rejected the error text explains why.
    """
    try:
        return bq_client.run_readonly_sql(sql)
    except Exception as error:
        return {"error": f"sql failed: {error}"}


if __name__ == "__main__":
    mcp.run(transport="stdio")
