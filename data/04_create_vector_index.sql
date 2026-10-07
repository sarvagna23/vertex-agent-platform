-- Step 4 (optional): an IVF index makes VECTOR_SEARCH approximate but faster.
-- BigQuery needs at least 5000 rows in the table to build an index.
-- Until the index finishes building, VECTOR_SEARCH silently falls back to brute force.
-- For your eval, report whether the number came from brute force or from the index.

CREATE OR REPLACE VECTOR INDEX complaint_embeddings_idx
ON `__PROJECT__.__DATASET__.complaint_embeddings`(embedding)
OPTIONS (index_type = 'IVF', distance_type = 'COSINE');
