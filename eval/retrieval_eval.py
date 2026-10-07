"""Retrieval quality: hit@1, hit@5 and MRR for BigQuery vector search on a labeled query set.

A query is a HIT at rank r when the result at rank r has a product containing any of the
expected substrings (case insensitive). Substrings are used because CFPB renamed several
products over the years, so exact matching would undercount.

Run:  python -m eval.retrieval_eval
"""
import json
import statistics
import time
from pathlib import Path

from mcp_server import bq_client

EVAL_DIR = Path(__file__).parent
QUERIES_FILE = EVAL_DIR / "labeled_queries.jsonl"
RESULTS_FILE = EVAL_DIR / "results" / "retrieval.json"
TOP_K = 5


def load_queries() -> list[dict]:
    with open(QUERIES_FILE) as handle:
        return [json.loads(line) for line in handle if line.strip()]


def first_hit_rank(results: list[dict], expected_products: list[str]) -> int | None:
    """1-based rank of the first result whose product matches, or None if nothing matches."""
    for rank, row in enumerate(results, start=1):
        product = (row.get("product") or "").lower()
        if any(expected.lower() in product for expected in expected_products):
            return rank
    return None


def main() -> None:
    queries = load_queries()
    per_query = []
    latencies_ms = []

    for item in queries:
        started_at = time.perf_counter()
        results = bq_client.vector_search(item["query"], top_k=TOP_K)
        latencies_ms.append((time.perf_counter() - started_at) * 1000)

        rank = first_hit_rank(results, item["expected_products"])
        per_query.append({"query": item["query"], "first_hit_rank": rank})
        print(f"rank={rank}  {item['query'][:70]}")

    total = len(per_query)
    hits_at_1 = sum(1 for row in per_query if row["first_hit_rank"] == 1)
    hits_at_5 = sum(1 for row in per_query if row["first_hit_rank"] is not None)
    reciprocal_ranks = [1 / row["first_hit_rank"] if row["first_hit_rank"] else 0 for row in per_query]

    sorted_latencies = sorted(latencies_ms)
    summary = {
        "queries": total,
        "top_k": TOP_K,
        "hit_at_1": round(hits_at_1 / total, 3),
        "hit_at_5": round(hits_at_5 / total, 3),
        "mrr": round(statistics.mean(reciprocal_ranks), 3),
        "retrieval_latency_ms_p50": round(statistics.median(sorted_latencies)),
        "retrieval_latency_ms_p95": round(sorted_latencies[min(total - 1, int(total * 0.95))]),
    }

    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_FILE.write_text(json.dumps({"summary": summary, "per_query": per_query}, indent=2))
    print("\n" + json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
