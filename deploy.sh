#!/usr/bin/env bash
# Build and deploy the API to Cloud Run with a least-privilege service account.
#
# Usage:   GOOGLE_CLOUD_PROJECT=my-proj ./deploy.sh
set -euo pipefail

PROJECT="${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
DATASET="${BQ_DATASET:-complaints}"
SERVICE="vertex-agent-platform"
SA_NAME="agent-api"
SA_EMAIL="$SA_NAME@$PROJECT.iam.gserviceaccount.com"

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  aiplatform.googleapis.com bigquery.googleapis.com --project "$PROJECT"

# Service account: can run queries, read ONLY the complaints dataset, and call Vertex AI.
gcloud iam service-accounts create "$SA_NAME" --project "$PROJECT" 2>/dev/null || echo "service account exists"
gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA_EMAIL" \
  --role="roles/bigquery.jobUser" --condition=None >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA_EMAIL" \
  --role="roles/aiplatform.user" --condition=None >/dev/null
# Needed so queries can call the remote embedding model through vertex_conn.
gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA_EMAIL" \
  --role="roles/bigquery.connectionUser" --condition=None >/dev/null

# Dataset level read access. The agents cannot read any other dataset in the project.
# (Same thing in the console: dataset > Sharing > Permissions > BigQuery Data Viewer.)
bq query --use_legacy_sql=false --project_id="$PROJECT" --location=US \
  "GRANT \`roles/bigquery.dataViewer\` ON SCHEMA \`$PROJECT.$DATASET\` TO 'serviceAccount:$SA_EMAIL'"

gcloud run deploy "$SERVICE" \
  --source . \
  --project "$PROJECT" --region "$REGION" \
  --service-account "$SA_EMAIL" \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=$REGION,BQ_DATASET=$DATASET" \
  --memory 1Gi --timeout 300 \
  --no-allow-unauthenticated

echo "Deployed. Test with:"
echo "  curl -H \"Authorization: Bearer \$(gcloud auth print-identity-token)\" \\"
echo "    -H 'Content-Type: application/json' -d '{\"question\":\"Why do people complain about overdraft fees?\"}' \\"
echo "    \$(gcloud run services describe $SERVICE --region $REGION --format='value(status.url)')/ask"
