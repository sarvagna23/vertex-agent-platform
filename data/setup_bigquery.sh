#!/usr/bin/env bash
# One-shot data layer setup: connection, IAM, subset, embedding model, embeddings, vector index.
#
# Usage:   GOOGLE_CLOUD_PROJECT=my-proj ./data/setup_bigquery.sh
# Smoke test first with a small subset:   ROWS=5000 GOOGLE_CLOUD_PROJECT=my-proj ./data/setup_bigquery.sh
set -euo pipefail

PROJECT="${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
DATASET="${BQ_DATASET:-complaints}"
ROWS="${ROWS:-50000}"
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "== Enabling APIs"
gcloud services enable bigquery.googleapis.com bigqueryconnection.googleapis.com \
  aiplatform.googleapis.com --project "$PROJECT"

echo "== Creating the Vertex connection (skipped if it exists)"
bq mk --connection --location=US --project_id="$PROJECT" \
  --connection_type=CLOUD_RESOURCE vertex_conn 2>/dev/null || echo "connection already exists"

echo "== Granting the connection service account access to Vertex AI"
CONN_SA="$(bq show --connection --format=json "$PROJECT.US.vertex_conn" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["cloudResource"]["serviceAccountId"])')"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:$CONN_SA" --role="roles/aiplatform.user" --condition=None >/dev/null
echo "granted roles/aiplatform.user to $CONN_SA (IAM can take a minute to propagate)"
sleep 30

run_sql() {
  local file="$1"
  echo "== Running $(basename "$file")"
  sed -e "s/__PROJECT__/$PROJECT/g" -e "s/__DATASET__/$DATASET/g" -e "s/__ROWS__/$ROWS/g" "$file" \
    | bq query --use_legacy_sql=false --location=US --project_id="$PROJECT"
}

run_sql "$HERE/01_create_subset.sql"
run_sql "$HERE/02_create_embedding_model.sql"
run_sql "$HERE/03_generate_embeddings.sql"

if [ "$ROWS" -ge 5000 ]; then
  run_sql "$HERE/04_create_vector_index.sql"
else
  echo "== Skipping vector index (needs at least 5000 rows)"
fi

echo "== Done. Row count:"
bq query --use_legacy_sql=false --location=US --project_id="$PROJECT" \
  "SELECT COUNT(*) AS embedded_rows FROM \`$PROJECT.$DATASET.complaint_embeddings\`"
