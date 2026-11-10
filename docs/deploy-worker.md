# Worker のデプロイ手順（Cloud Run）

- 作成: 2026-11-07（B）／対象: `Dockerfile`、`scripts/deploy_worker.sh`
- Worker は API とは**別の Cloud Run サービス**。Cloud Tasks だけが呼べる（認証付き、公開しない）。
- 状態: **ローカル統合案・実環境未検証**。A側の永続IO/SinkをBの実handler/jobsに接続した。
  `SERVICE_ROLE=worker` で `api.worker:app` を起動する。元の `worker.main:app` はログ専用のまま保持する。
- 以下の本番操作は未実施。ユーザーの承認と設定レビューを得てから、人間の在席時に行う。
  ローカル検証はFirebase Emulator/AIモックのみを使う。詳細は integration-handoff.md。

## 1. 1回だけ必要な準備（マスターの操作）

```bash
gcloud auth login                    # ブラウザで Google アカウントにログイン
gcloud config set project gesture-relay-game
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com cloudtasks.googleapis.com aiplatform.googleapis.com
```

## 2. 実行権限（Worker が使うサービスアカウント）

Cloud Run は、既定で「Compute Engine のサービスアカウント」で動く。このアカウントに、次を付ける。

| 役割 | 用途 |
|---|---|
| Vertex AI ユーザー（`roles/aiplatform.user`） | AI の呼び出し（キー不要） |
| Storage オブジェクト管理者（`roles/storage.objectAdmin`）。バケット `gesture-relay-game-assets` に限定 | 画像・録画の保存と削除 |
| Cloud Datastore ユーザー（`roles/datastore.user`） | Firestore の読み書き |

## 3. デプロイ

```bash
# 承認後に値をレビューしてexportする（この文書の値は実行済み設定ではない）。
export TASKS_LOCATION='<queue-region>' TASKS_QUEUE='<queue-name>'
export WORKER_URL='https://<worker-service>/tasks/run'
export DEADLINE_URL='https://<deadline-service>/internal/deadlines'
export TASKS_SERVICE_ACCOUNT='<delivery-sa-email>'
export INTERNAL_AUDIENCE='https://<worker-service>'
ENABLE_CLOUD=true ./scripts/deploy_worker.sh  # AIはモック、データ保存先は実環境
# 実AIも別途承認後: AI_MODE=real ENABLE_CLOUD=true ./scripts/deploy_worker.sh
```

- ビルドは Cloud Build が行う（手元に Docker は不要）。
- 設定値は環境変数で渡す。`SERVICE_ROLE=worker`、`RUNTIME_MODE=cloud` と明示opt-inが必要。
  既存B名の `GCP_PROJECT` / `STORAGE_BUCKET` はA名 `PROJECT_ID` / `BUCKET_NAME` に互換対応する。
  `ENABLE_CLOUD=true` と必須設定がなければスクリプトはgcloudを呼ぶ前に停止する。
  自動.env読込は行わない。Vertexは実行アカウント、Developer APIは承認済みSecretで認証する。
- Gemini API（キー）も併用する場合は、Secret Manager に入れて `--set-secrets GEMINI_API_KEY=GEMINI_API_KEY:latest` を足す。

## 4. 動作確認

```bash
URL=$(gcloud run services describe worker --region asia-northeast1 --format='value(status.url)')
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" $URL/health
```
- `{"ok":true}` が返れば成功。トークン無しで呼ぶと 403 になる（それが正しい）。

## 5. Cloud Tasks から呼ぶ設定（A と相談）

- 承認済み役割表では、キュー/Worker基盤はB、APIからの配送はA。キュー作成担当の文書差異は要確認。
- Tasks配送サービスアカウントにWorkerの `roles/run.invoker` を付け、enqueueする側には配送SAの利用権限をレビューする。
- タスクの宛先は `POST {URL}/tasks/run`、認証は OIDC トークン。本文は `JobPayload` の JSON。
- 再試行はCloud Tasksが配送し、DBの試行数で合計3回まで。再試行する失敗は500、確定は200。
  結果保存後の進行失敗はprogress_outbox、推論中の停止はexecution_outboxで回復する。
  heartbeat/期限サービスの保守処理が動く前提であり、ゼロ台時の回復時間・IAMは実環境検証待ち。

### キューの実際（2026-11-08 作成済み）

| 項目 | 値 |
|---|---|
| 名前 / 場所 | `gesture-jobs` / `asia-northeast1` |
| 最大試行 | 3（`JOB_POLICY` と一致）。`X-CloudTasks-TaskRetryCount` は 0〜2、Worker は +1 して 1〜3 回目と数える |
| 再試行の間隔 | 5秒から、最大60秒（倍々で増える。最大4回まで） |
| 同時実行 | 4（画像生成を同時に4件投げると429が出たため、10から下げた） |

注文を送るアカウントの作成と権限（**IAM の変更なので、マスターか A が実行する**）:

```bash
gcloud iam service-accounts create tasks-invoker --project gesture-relay-game \
  --display-name "Cloud Tasks から Worker を呼ぶ"
# このアカウントに Worker を呼ぶ権限
gcloud run services add-iam-policy-binding worker --project gesture-relay-game --region asia-northeast1 \
  --member "serviceAccount:tasks-invoker@gesture-relay-game.iam.gserviceaccount.com" --role roles/run.invoker
# A の API が、このアカウントとして注文を送れる権限（API の実行アカウント名は A に確認）
gcloud iam service-accounts add-iam-policy-binding tasks-invoker@gesture-relay-game.iam.gserviceaccount.com \
  --project gesture-relay-game --member "serviceAccount:<APIの実行アカウント>" --role roles/iam.serviceAccountUser
# API の実行アカウントが、キューへ入れる権限
gcloud projects add-iam-policy-binding gesture-relay-game \
  --member "serviceAccount:<APIの実行アカウント>" --role roles/cloudtasks.enqueuer
```

## 6. 設定の意味

| オプション | 値 | 理由 |
|---|---|---|
| `--timeout` | 120秒 | 現在のAI待機上限60秒に余裕を置く案。実モデル遅延は未検証 |
| `--concurrency` | 4 | 1台で同時に4件まで処理 |
| `--max-instances` | 5 | 費用の暴走を防ぐ上限 |
| `--no-allow-unauthenticated` | — | 外から直接呼ばせない |
