#!/usr/bin/env bash
# 非常ボタン: 費用や乱用が急に増えたとき、API を外から呼べなくする（マスターが自分で実行する）。
# Issue #18（匿名ログインによる、部屋作成・AI ジョブの乱用）の備え。Worker・期限処理は、もともと非公開。
#
#   止める:   bash scripts/emergency_stop.sh stop     （API の公開をやめる＝allUsers の呼び出し権限を外す）
#   再開する: bash scripts/emergency_stop.sh start    （API を、もう一度公開する）
#   状態:     bash scripts/emergency_stop.sh status
#
# ⚠ 運営のルール: 提出締切（11/10 19:00）〜11/14 は、実行環境を凍結し、デプロイ URL の稼働を維持する。
#   API を止めると、この「稼働の維持」と衝突する。凍結中は、費用の急増など、本当の緊急時だけ。使う前に、運営に相談する。
# 止めると、ゲームは遊べなくなる（画面は出るが、API が 403 になる）。Scheduler と進行中のゲームの回復は、影響を受けない。
set -euo pipefail

PROJECT="${GCP_PROJECT:-gesture-relay-game}"
REGION="${REGION:-asia-northeast1}"
SERVICE="${SERVICE:-gesture-relay-api}"
MODE="${1:-status}"

case "$MODE" in
  stop)
    gcloud run services remove-iam-policy-binding "$SERVICE" --project "$PROJECT" --region "$REGION" \
      --member=allUsers --role=roles/run.invoker --quiet
    echo "停止しました（API の公開をやめた）。再開: bash scripts/emergency_stop.sh start"
    ;;
  start)
    gcloud run services add-iam-policy-binding "$SERVICE" --project "$PROJECT" --region "$REGION" \
      --member=allUsers --role=roles/run.invoker --quiet
    echo "再開しました（API を公開した）。"
    ;;
  status)
    echo "API を呼べる人:"
    gcloud run services get-iam-policy "$SERVICE" --project "$PROJECT" --region "$REGION" --format='value(bindings.role,bindings.members)'
    ;;
  *)
    echo "使い方: bash scripts/emergency_stop.sh [stop|start|status]" >&2
    exit 2
    ;;
esac
