"""LLM-as-a-Judge with the Vertex AI Gen AI evaluation service, plus a deterministic PII leak check.

For each labeled question we run the full agent workflow, then ask a judge model to score the
answer for groundedness (is it supported by the retrieved evidence), answer quality and fluency.

Run:  python -m eval.judge_eval --n 15

NOTE: the Vertex AI evaluation SDK has been evolving. If the import below fails, check the
current "Gen AI evaluation service" docs for the up-to-date EvalTask and metric names.
"""
import argparse
import asyncio
import json
from pathlib import Path

import pandas as pd
import vertexai
from vertexai.evaluation import EvalTask, MetricPromptTemplateExamples

import config
from agents.runner import run_pipeline
from pii.redactor import redact_pii

EVAL_DIR = Path(__file__).parent
RESULTS_FILE = EVAL_DIR / "results" / "judge.json"


async def collect_answers(questions: list[str]) -> list[dict]:
    """Run the workflow one question at a time (keeps Gemini rate limits happy)."""
    rows = []
    for question in questions:
        result = await run_pipeline(question)
        rows.append(
            {
                "prompt": question,
                "response": result["answer"],
                # The judge sees the same evidence the responder saw.
                "context": f"{result['retrieved']}\n\n{result['analysis']}",
            }
        )
        print(f"answered: {question[:70]}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=15)
    args = parser.parse_args()

    with open(EVAL_DIR / "labeled_queries.jsonl") as handle:
        questions = [json.loads(line)["query"] for line in handle if line.strip()][: args.n]

    rows = asyncio.run(collect_answers(questions))
    dataset = pd.DataFrame(rows)

    # Deterministic check: run the redactor over every answer. Any hit means PII leaked out.
    leaks = [bool(redact_pii(text).found_pii) for text in dataset["response"]]
    pii_leak_rate = sum(leaks) / len(leaks)

        # Judge model scoring. The groundedness judge grades against the prompt text only,
    # so for that metric the evidence goes INSIDE the prompt. The other metrics keep the plain question.
    vertexai.init(project=config.PROJECT_ID, location=config.LOCATION)

    grounded_dataset = dataset.copy()
    grounded_dataset["prompt"] = "Evidence:\n" + dataset["context"] + "\n\nQuestion: " + dataset["prompt"]
    grounded_result = EvalTask(
        dataset=grounded_dataset,
        metrics=[MetricPromptTemplateExamples.Pointwise.GROUNDEDNESS],
    ).evaluate()

    quality_result = EvalTask(
        dataset=dataset,
        metrics=[
            MetricPromptTemplateExamples.Pointwise.QUESTION_ANSWERING_QUALITY,
            MetricPromptTemplateExamples.Pointwise.FLUENCY,
        ],
    ).evaluate()

    # Keep the judge's reasoning per row, so any low score can be inspected later.
    grounded_result.metrics_table.to_csv(EVAL_DIR / "results" / "judge_groundedness.csv", index=False)

    judge_metrics = {}
    for result in (grounded_result, quality_result):
        for key, value in result.summary_metrics.items():
            if isinstance(value, (int, float)) and key != "row_count":
                judge_metrics[key] = round(float(value), 3)

    summary = {
        "questions": len(dataset),
        "pii_leak_rate": round(pii_leak_rate, 3),
        "judge_summary_metrics": judge_metrics,
    }
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_FILE.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
