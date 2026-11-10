#!/usr/bin/env bash
# API/期限処理の専用実行アカウントに、最小限の権限を付ける（マスターが自分で実行する）。
# 実行前に、中身を確認すること。取り消しは、同じ内容の remove-iam-policy-binding。
# 実行: bash scripts/grant_runtime_iam.sh
set -euo pipefail

PROJECT="${GCP_PROJECT:-gesture-relay-game}"
REGION="${TASKS_LOCATION:-asia-northeast1}"
QUEUE="${TASKS_QUEUE:-gesture-jobs}"
BUCKET="${BUCKET:-gesture-relay-game-assets}"
INVOKER="tasks-invoker@${PROJECT}.iam.gserviceaccount.com"
API_SA="api-runtime@${PROJECT}.iam.gserviceaccount.com"
DEADLINE_SA="deadline-runtime@${PROJECT}.iam.gserviceaccount.com"

for SA in "$API_SA" "$DEADLINE_SA"; do
  echo "== ${SA}"
  # Firestore の読み書き
  gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:${SA}" --role roles/datastore.user --condition=None --quiet >/dev/null
  # キュー gesture-jobs にだけ、ジョブを積める
  gcloud tasks queues add-iam-policy-binding "$QUEUE" --location "$REGION" --project "$PROJECT" \
    --member "serviceAccount:${SA}" --role roles/cloudtasks.enqueuer --quiet >/dev/null
  # バケット gesture-relay-game-assets にだけ、ファイルの読み書き・削除
  gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" --member "serviceAccount:${SA}" --role roles/storage.objectUser --quiet >/dev/null
  # 配送用アカウント tasks-invoker を、指名してジョブを積める
  gcloud iam service-accounts add-iam-policy-binding "$INVOKER" --project "$PROJECT" \
    --member "serviceAccount:${SA}" --role roles/iam.serviceAccountUser --quiet >/dev/null
done

# API だけ: ログイン情報の失効確認（check_revoked）のために、ユーザー情報を読む
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:${API_SA}" --role roles/firebaseauth.viewer --condition=None --quiet >/dev/null
echo "完了。確認: gcloud projects get-iam-policy ${PROJECT} --flatten=bindings --filter='bindings.members:runtime' --format='table(bindings.role,bindings.members)'"
