-- Step 1: copy a reproducible subset of the public CFPB complaints into our own dataset.
-- Only complaints that have a written narrative are useful for semantic search.
-- __PROJECT__, __DATASET__ and __ROWS__ are replaced by setup_bigquery.sh.
-- If the column list fails, check the public schema:
--   bq show --schema --format=prettyjson bigquery-public-data:cfpb_complaints.complaint_database

CREATE SCHEMA IF NOT EXISTS `__PROJECT__.__DATASET__` OPTIONS (location = 'US');

CREATE OR REPLACE TABLE `__PROJECT__.__DATASET__.complaints_raw` AS
SELECT
  complaint_id,
  date_received,
  product,
  subproduct,
  issue,
  subissue,
  consumer_complaint_narrative AS narrative,
  company_name,
  state,
  company_response_to_consumer,
  timely_response
FROM `bigquery-public-data.cfpb_complaints.complaint_database`
WHERE consumer_complaint_narrative IS NOT NULL
  AND LENGTH(consumer_complaint_narrative) > 100
ORDER BY FARM_FINGERPRINT(complaint_id)  -- stable pseudo-random order, so reruns give the same subset
LIMIT __ROWS__;
