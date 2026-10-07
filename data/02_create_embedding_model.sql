-- Step 2: a BigQuery remote model that calls the Vertex AI text embedding model.
-- Needs the Cloud resource connection created by setup_bigquery.sh (named vertex_conn).
-- Check the current embedding model name in the Vertex AI docs if this endpoint is rejected.

CREATE OR REPLACE MODEL `__PROJECT__.__DATASET__.embedding_model`
  REMOTE WITH CONNECTION `__PROJECT__.US.vertex_conn`
  OPTIONS (ENDPOINT = 'text-embedding-005');
