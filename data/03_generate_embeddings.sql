-- Step 3: embed every narrative and store the vectors next to the metadata.
-- flatten_json_output returns the vector as ARRAY<FLOAT64> in ml_generate_embedding_result.
-- Narratives are cut to 6000 characters to stay under the model's input token limit.

CREATE OR REPLACE TABLE `__PROJECT__.__DATASET__.complaint_embeddings` AS
SELECT
  complaint_id,
  product,
  issue,
  narrative,
  ml_generate_embedding_result AS embedding
FROM ML.GENERATE_EMBEDDING(
  MODEL `__PROJECT__.__DATASET__.embedding_model`,
  (
    SELECT complaint_id, product, issue, narrative, SUBSTR(narrative, 1, 6000) AS content
    FROM `__PROJECT__.__DATASET__.complaints_raw`
  ),
  STRUCT(TRUE AS flatten_json_output)
)
WHERE ARRAY_LENGTH(ml_generate_embedding_result) > 0;  -- drop rows where the embedding call failed
