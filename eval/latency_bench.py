"""End to end latency of the deployed /ask endpoint (p50 and p95).

Run:  python -m eval.latency_bench --url https://YOUR-SERVICE.run.app --n 20
Add --token "$(gcloud auth print-identity-token)" if the Cloud Run service requires auth.
"""
import argparse
import json
import statistics
from pathlib import Path

import httpx

EVAL_DIR = Path(__file__).parent
RESULTS_FILE = EVAL_DIR / "results" / "latency.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Base URL of the service")
    parser.add_argument("--n", type=int, default=20, help="Number of requests")
    parser.add_argument("--token", default=None, help="Optional identity token")
    args = parser.parse_args()

    with open(EVAL_DIR / "labeled_queries.jsonl") as handle:
        questions = [json.loads(line)["query"] for line in handle if line.strip()]

    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    latencies_ms = []
    failures = 0

    with httpx.Client(timeout=180, headers=headers) as client:
        for index in range(args.n):
            question = questions[index % len(questions)]
            try:
                response = client.post(f"{args.url}/ask", json={"question": question})
                response.raise_for_status()
                latencies_ms.append(response.json()["latency_ms"])
            except Exception as error:
                failures += 1
                print(f"request {index} failed: {error}")

    if not latencies_ms:
        raise SystemExit("All requests failed.")

    ordered = sorted(latencies_ms)
    summary = {
        "requests": args.n,
        "failures": failures,
        "latency_ms_p50": round(statistics.median(ordered)),
        "latency_ms_p95": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "note": "latency_ms is measured inside the service (agent workflow only, no network)",
    }
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_FILE.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
