#!/usr/bin/env bash
# Worker を Cloud Run にデプロイする。認証付き（Cloud Tasks だけが呼べる）で公開しない。
set -euo pipefail

PROJECT="${PROJECT:-gesture-relay-game}"
REGION="${REGION:-asia-northeast1}"
SERVICE="${SERVICE:-worker}"
BUCKET="${BUCKET:-gesture-relay-game-assets}"
AI_MODE="${AI_MODE:-mock}"   # 本物のAIは AI_MODE=real ./scripts/deploy_worker.sh

# This script is never run against a real project by local tests. The merged
# image defaults to the API role and refuses cloud access until explicitly enabled.
if [[ "${ENABLE_CLOUD:-false}" != "true" ]]; then
  echo 'Not executed: explicit ENABLE_CLOUD=true authorization and reviewed settings are required.' >&2
  exit 2
fi
for name in TASKS_LOCATION TASKS_QUEUE WORKER_URL DEADLINE_URL TASKS_SERVICE_ACCOUNT INTERNAL_AUDIENCE; do
  if [[ -z "${!name:-}" ]]; then
    echo "Not executed: missing required setting ${name}." >&2
    exit 2
  fi
done

cd "$(dirname "$0")/.."
# WORKER_SA を指定すると、その専用アカウントで動かす（未指定は、これまでどおり既定のアカウント）。
# 専用アカウントの作成と権限は scripts/grant_worker_iam.sh（Issue #31）。
SA_ARGS=()
if [[ -n "${WORKER_SA:-}" ]]; then
  SA_ARGS=(--service-account "${WORKER_SA}")
fi
gcloud run deploy "$SERVICE" \
  --project "$PROJECT" --region "$REGION" --source . \
  "${SA_ARGS[@]+"${SA_ARGS[@]}"}" \
  --no-allow-unauthenticated --quiet --verbosity=info \
  --timeout 120 --concurrency 4 --max-instances 5 \
  --set-env-vars "SERVICE_ROLE=worker,RUNTIME_MODE=cloud,ENABLE_CLOUD=true,AI_MODE=${AI_MODE},STORAGE_MODE=gcs,STORAGE_BUCKET=${BUCKET},GCP_PROJECT=${PROJECT},TASKS_LOCATION=${TASKS_LOCATION},TASKS_QUEUE=${TASKS_QUEUE},WORKER_URL=${WORKER_URL},DEADLINE_URL=${DEADLINE_URL},TASKS_SERVICE_ACCOUNT=${TASKS_SERVICE_ACCOUNT},INTERNAL_AUDIENCE=${INTERNAL_AUDIENCE}"
