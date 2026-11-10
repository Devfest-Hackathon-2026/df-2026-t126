#!/usr/bin/env bash
# Worker の専用実行アカウント worker-runtime を作り、最小限の権限を付ける（マスターが自分で実行する）。
# Issue #31（Worker が、プロジェクト全体の Editor 権限を持つ標準アカウントで動いている）の対策。
# 実行前に、中身を確認すること。取り消しは、同じ内容の remove-iam-policy-binding。
# 実行: bash scripts/grant_worker_iam.sh
# このあと: WORKER_SA=worker-runtime@gesture-relay-game.iam.gserviceaccount.com で scripts/deploy_worker.sh を実行する。
# 戻し方: gcloud run services update-traffic worker --region asia-northeast1 --to-revisions=<前のリビジョン>=100
set -euo pipefail

PROJECT="${GCP_PROJECT:-gesture-relay-game}"
REGION="${TASKS_LOCATION:-asia-northeast1}"
QUEUE="${TASKS_QUEUE:-gesture-jobs}"
BUCKET="${BUCKET:-gesture-relay-game-assets}"
INVOKER="tasks-invoker@${PROJECT}.iam.gserviceaccount.com"
SA_NAME="worker-runtime"
SA="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "$SA" --project "$PROJECT" >/dev/null 2>&1; then
  echo "== ${SA} を作成"
  gcloud iam service-accounts create "$SA_NAME" --project "$PROJECT" --display-name "Worker runtime (least privilege)"
  # 作成の直後は、IAM 側にまだ反映されず「does not exist」になることがある。少し待つ（2026-11-09 に発生）
  echo "反映を待っています（20秒）"
  sleep 20
fi

echo "== ${SA} に権限を付ける"
# Firestore の読み書き（ジョブの結果を書く）
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:${SA}" --role roles/datastore.user --condition=None --quiet >/dev/null
# Vertex AI（Gemini）の呼び出し。鍵は使わず、この権限で認証する
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:${SA}" --role roles/aiplatform.user --condition=None --quiet >/dev/null
# キュー gesture-jobs にだけ、次のジョブを積める（Worker も、完了後に次の段のタスクを積む）
gcloud tasks queues add-iam-policy-binding "$QUEUE" --location "$REGION" --project "$PROJECT" \
  --member "serviceAccount:${SA}" --role roles/cloudtasks.enqueuer --quiet >/dev/null
# バケット gesture-relay-game-assets にだけ、画像の読み書き
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" --member "serviceAccount:${SA}" --role roles/storage.objectUser --quiet >/dev/null
# 配送用アカウント tasks-invoker を、指名してタスクを積める
gcloud iam service-accounts add-iam-policy-binding "$INVOKER" --project "$PROJECT" \
  --member "serviceAccount:${SA}" --role roles/iam.serviceAccountUser --quiet >/dev/null

echo "完了。確認:"
echo "  gcloud projects get-iam-policy ${PROJECT} --flatten=bindings --filter='bindings.members:${SA_NAME}' --format='table(bindings.role,bindings.members)'"
