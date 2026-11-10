#!/usr/bin/env bash
# A の API と期限処理サービスを Cloud Run に配備する（マスターの承認後にだけ実行）。
# Worker は scripts/deploy_worker.sh。AI は呼ばない（AI_MODE=mock）。
#   ENABLE_CLOUD=true ./scripts/deploy_a_services.sh deadlines   # 先に。URL ができる
#   ENABLE_CLOUD=true ./scripts/deploy_a_services.sh api         # 次に
set -euo pipefail

PROJECT="${PROJECT:-gesture-relay-game}"
REGION="${REGION:-asia-northeast1}"
NUM="${PROJECT_NUMBER:-122800925175}"
BUCKET="${BUCKET:-gesture-relay-game-assets}"
QUEUE="${TASKS_QUEUE:-gesture-jobs}"
INVOKER="tasks-invoker@${PROJECT}.iam.gserviceaccount.com"
# Cloud Run の URL は「サービス名-プロジェクト番号.リージョン.run.app」で決まる（配備後に実URLと照合する）
DEADLINE_BASE="https://gesture-relay-deadlines-${NUM}.${REGION}.run.app"
WORKER_BASE="https://worker-${NUM}.${REGION}.run.app"

if [[ "${ENABLE_CLOUD:-false}" != "true" ]]; then
  echo 'Not executed: explicit ENABLE_CLOUD=true authorization is required.' >&2; exit 2
fi
ROLE="${1:-}"
# DROPOUT_AFTER_S: 生存確認が途絶えて「退出」とみなす秒数。既定は15秒だが、本番で API が一時的に遅れると、誤って退出になった（2026-11-09 22:30）。30秒にする（人間の承認のもと）。
COMMON="RUNTIME_MODE=cloud,ENABLE_CLOUD=true,AI_MODE=mock,PROJECT_ID=${PROJECT},BUCKET_NAME=${BUCKET},TASKS_LOCATION=${REGION},TASKS_QUEUE=${QUEUE},WORKER_URL=${WORKER_BASE}/tasks/run,DEADLINE_URL=${DEADLINE_BASE}/internal/deadlines,TASKS_SERVICE_ACCOUNT=${INVOKER},INTERNAL_AUDIENCE=${DEADLINE_BASE},DROPOUT_AFTER_S=${DROPOUT_AFTER_S:-30}"

cd "$(dirname "$0")/.."
case "$ROLE" in
  deadlines)
    # 非公開（Cloud Tasks / Scheduler だけが呼べる）
    gcloud run deploy gesture-relay-deadlines --project "$PROJECT" --region "$REGION" --source . \
      --service-account "deadline-runtime@${PROJECT}.iam.gserviceaccount.com" \
      --no-allow-unauthenticated --quiet --timeout 180 --concurrency 8 --max-instances 2 \
      --set-env-vars "SERVICE_ROLE=deadlines,${COMMON}"
    gcloud run services add-iam-policy-binding gesture-relay-deadlines --project "$PROJECT" --region "$REGION" \
      --member "serviceAccount:${INVOKER}" --role roles/run.invoker --quiet
    gcloud run services describe gesture-relay-deadlines --project "$PROJECT" --region "$REGION" --format='value(status.url)'
    ;;
  api)
    # 公開するかどうかは別承認。既定は非公開（PUBLIC_API=true で公開）
    AUTH="--no-allow-unauthenticated"; [[ "${PUBLIC_API:-false}" == "true" ]] && AUTH="--allow-unauthenticated"
    gcloud run deploy gesture-relay-api --project "$PROJECT" --region "$REGION" --source . \
      --service-account "api-runtime@${PROJECT}.iam.gserviceaccount.com" \
      $AUTH --quiet --timeout 60 --concurrency 8 --max-instances 2 \
      --set-env-vars "SERVICE_ROLE=api,${COMMON}"
    gcloud run services describe gesture-relay-api --project "$PROJECT" --region "$REGION" --format='value(status.url)'
    ;;
  *) echo "使い方: ENABLE_CLOUD=true $0 deadlines|api" >&2; exit 2 ;;
esac
