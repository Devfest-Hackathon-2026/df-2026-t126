# A の API・期限処理の配備計画（B 担当 AI が代行／未実行）

A の AI が使えなくなったため、配備と設定だけを B が代行する。**A のコードは変更しない。** 実行はすべてマスターの承認後。

## 順番
| # | 作業 | 実行 | 承認 | 費用 |
|---|---|---|---|---|
| 1 | 期限処理サービス `gesture-relay-deadlines` を配備（非公開）。`tasks-invoker` に起動権限 | `ENABLE_CLOUD=true scripts/deploy_a_services.sh deadlines` | 要 | 小（使った分だけ。最大2台） |
| 2 | API サービス `gesture-relay-api` を配備 | `ENABLE_CLOUD=true scripts/deploy_a_services.sh api` | 要 | 同上 |
| 3 | Worker を再デプロイ（`DEADLINE_URL`、お題44件） | `scripts/deploy_worker.sh`（値は下記） | 要 | 同上 |
| 4 | API の公開（フロントの `/api/**` から呼ぶため） | `PUBLIC_API=true` で 2 を再実行、または Hosting の接続 | **別承認** | なし |
| 5 | 毎分の回復（Scheduler）。PR #7 の取り込み後 | Cloud Scheduler 作成 | 別承認 | ほぼなし |

## URL（Cloud Run が自動で決める形。配備後に実URLと照合する）
- 期限: `https://gesture-relay-deadlines-122800925175.asia-northeast1.run.app`
- Worker: `https://worker-122800925175.asia-northeast1.run.app`（既存）
- 期限の配備後、実URLが上と違えば、設定を直して再配備する。

## 3 の Worker 再デプロイの値
```bash
ENABLE_CLOUD=true AI_MODE=real TASKS_LOCATION=asia-northeast1 TASKS_QUEUE=gesture-jobs \
WORKER_URL=https://worker-122800925175.asia-northeast1.run.app/tasks/run \
DEADLINE_URL=https://gesture-relay-deadlines-122800925175.asia-northeast1.run.app/internal/deadlines \
TASKS_SERVICE_ACCOUNT=tasks-invoker@gesture-relay-game.iam.gserviceaccount.com \
INTERNAL_AUDIENCE=https://worker-122800925175.asia-northeast1.run.app \
scripts/deploy_worker.sh
```

## 確認（配備後）
1. 期限: 認証なしで叩くと 401/403（非公開の確認）。
2. API: Firebase のログインつきで 14 本の API が通ること（フロントと一緒に）。
3. Worker: `scripts/smoke_real.py` 相当で 4 種のジョブが成功すること。
4. ログに、権限不足（403）が出ていないこと。

## ロールバック
- 配備前に、各サービスの現在のリビジョンを記録する（Worker の戻し先: `worker-00004-fdl`）。
- 新規のサービスは、戻し先がないので、`gcloud run services delete` で消せる（データは消えない）。

## 注意
- API と期限処理に、AI のキーや Secret Manager の権限は与えない（`AI_MODE=mock`）。
- 期限処理は、PR #7 が取り込まれるまで `/internal/maintenance` を持たない。取り込み後に再配備が要る。
- CORS は、フロントが Hosting の同じドメインから呼ぶ前提で空にしている。
