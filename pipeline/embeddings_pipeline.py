"""STRETCH: a Vertex AI Pipeline that embeds only the new complaints and appends them.

Compile and submit:
  python -m pipeline.embeddings_pipeline --project my-proj --bucket gs://my-bucket/pipeline-root
Needs requirements-extra.txt (kfp, google-cloud-aiplatform).
"""
import argparse

from kfp import compiler, dsl


@dsl.component(base_image="python:3.11", packages_to_install=["google-cloud-bigquery"])
def refresh_embeddings(project: str, dataset: str) -> int:
    """Embed complaints that are in the raw table but not yet in the embeddings table.

    Returns how many rows were added, so each pipeline run shows its effect.
    """
    from google.cloud import bigquery

    client = bigquery.Client(project=project, location="US")
    embeddings_table = f"{project}.{dataset}.complaint_embeddings"

    count_sql = f"SELECT COUNT(*) AS n FROM `{embeddings_table}`"
    rows_before = list(client.query(count_sql).result())[0].n

    insert_sql = f"""
    INSERT INTO `{embeddings_table}` (complaint_id, product, issue, narrative, embedding)
    SELECT complaint_id, product, issue, narrative, ml_generate_embedding_result
    FROM ML.GENERATE_EMBEDDING(
      MODEL `{project}.{dataset}.embedding_model`,
      (
        SELECT complaint_id, product, issue, narrative, SUBSTR(narrative, 1, 6000) AS content
        FROM `{project}.{dataset}.complaints_raw`
        WHERE complaint_id NOT IN (SELECT complaint_id FROM `{embeddings_table}`)
      ),
      STRUCT(TRUE AS flatten_json_output)
    )
    WHERE ARRAY_LENGTH(ml_generate_embedding_result) > 0
    """
    client.query(insert_sql).result()

    rows_after = list(client.query(count_sql).result())[0].n
    return int(rows_after - rows_before)


@dsl.pipeline(name="refresh-complaint-embeddings")
def embeddings_pipeline(project: str, dataset: str = "complaints"):
    refresh_embeddings(project=project, dataset=dataset)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--bucket", required=True, help="gs:// pipeline root")
    parser.add_argument("--region", default="us-central1")
    args = parser.parse_args()

    template_path = "embeddings_pipeline.json"
    compiler.Compiler().compile(embeddings_pipeline, template_path)

    from google.cloud import aiplatform

    aiplatform.init(project=args.project, location=args.region)
    job = aiplatform.PipelineJob(
        display_name="refresh-complaint-embeddings",
        template_path=template_path,
        pipeline_root=args.bucket,
        parameter_values={"project": args.project},
    )
    job.submit()
    print("Submitted. Watch it in the Vertex AI Pipelines console.")


if __name__ == "__main__":
    main()
