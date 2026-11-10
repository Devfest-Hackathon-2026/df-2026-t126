# Worker 再デプロイ手順書（A の永続化つき入口へ）

- 作成: 2026-11-08（B）／状態: **準備のみ。クラウドは変更していない。実行には人間の承認が要る**（`docs/pending-approvals.md` #3b）
- 目的: 現在の Worker（旧スタブ版、リビジョン `worker-00004-fdl`）を、A の永続化つき入口（`SERVICE_ROLE=worker` → `api.worker:app`）に置き換える。
- 前提: PR #2 は `main` にマージ済み（`8dce24b`）。統合後の全テスト 136 件合格。

## 1. 先に分かった重要な点

| 点 | 内容 |
|---|---|
| Worker も「注文を入れる側」になる | `advance_step` が、次の段のジョブや期限のタスクを、Cloud Tasks に入れる。だから Worker にも **キューへ入れる権限**と、**`tasks-invoker` として注文を送る権限（`iam.serviceAccountUser`）**が要る |
| `DEADLINE_URL` が必須 | A のクラウド設定は、`DEADLINE_URL` が空だと起動しない（`backend_a/runtime.py`）。**期限サービス（`SERVICE_ROLE=deadlines`）の URL が先に決まっている必要がある** |
| 認証の組み合わせ | Worker は、Cloud Tasks が付ける OIDC トークンを検証する。**`INTERNAL_AUDIENCE` は、`WORKER_URL` の「スキーム＋ホスト」と完全に同じ**にする。`TASKS_SERVICE_ACCOUNT` は、トークンの発行元（`tasks-invoker`）と一致させる |
| `WORKER_URL` は、パスを含む完全な URL | A の送信コードは、`WORKER_URL` をそのままタスクの宛先にする。**`/tasks/run` までを含める** |
| Cloud Run の URL | サービス名とプロジェクト番号から、**デプロイ前に決まる**形式がある: `https://<サービス名>-122800925175.asia-northeast1.run.app` |

## 2. 値の一覧

| 環境変数 | 値 | 状態 |
|---|---|---|
| `TASKS_LOCATION` | `asia-northeast1` | ✅ 確定（キュー作成済み） |
| `TASKS_QUEUE` | `gesture-jobs` | ✅ 確定 |
| `WORKER_URL` | `https://worker-122800925175.asia-northeast1.run.app/tasks/run` | ✅ 確定（サービス名 `worker` のまま） |
| `INTERNAL_AUDIENCE` | `https://worker-122800925175.asia-northeast1.run.app` | ✅ 確定 |
| `TASKS_SERVICE_ACCOUNT` | `tasks-invoker@gesture-relay-game.iam.gserviceaccount.com` | ✅ 作成済み |
| `DEADLINE_URL` | `https://<期限サービス名>-122800925175.asia-northeast1.run.app/internal/deadlines`（サービス名は **A が決める**） | ⬜ **A の返事待ち** |
| `BUCKET` | `gesture-relay-game-assets` | ✅ 確定 |
| `AI_MODE` | `real` | ✅ 確定 |
| `ENABLE_CLOUD` | `true` | 実行時に明示（承認の印） |

## 3. 実行順（承認後）

1. **（A）期限サービスと API を作る側の準備**: サービス名・URL を PR に書く。期限サービスが先でも、同時でもよい（URL は事前に決まるため、**Worker のデプロイ時点で、期限サービスが未作成でも起動はできる**。ただし、期限のタスクは、期限サービスができるまで失敗する）。
2. **✅ 実施済み（2026-11-08、マスターが自分で実行。B が確認）— 権限の追加**（IAM の変更。承認済みの #1 の残り）:
   ```bash
   # Worker の実行アカウント（既定の Compute SA。Editor 権限あり）が、tasks-invoker として注文を送れるようにする
   gcloud iam service-accounts add-iam-policy-binding tasks-invoker@gesture-relay-game.iam.gserviceaccount.com \
     --project gesture-relay-game \
     --member "serviceAccount:122800925175-compute@developer.gserviceaccount.com" \
     --role roles/iam.serviceAccountUser
   ```
   - キューへ入れる権限は、Editor 権限に含まれる想定。足りなければ `roles/cloudtasks.enqueuer` を追加する。
3. **（B）Worker をデプロイ**:
   ```bash
   cd ~/Documents/GitHub/gesture-relay-game && git pull
   ENABLE_CLOUD=true AI_MODE=real \
   TASKS_LOCATION=asia-northeast1 TASKS_QUEUE=gesture-jobs \
   WORKER_URL=https://worker-122800925175.asia-northeast1.run.app/tasks/run \
   INTERNAL_AUDIENCE=https://worker-122800925175.asia-northeast1.run.app \
   TASKS_SERVICE_ACCOUNT=tasks-invoker@gesture-relay-game.iam.gserviceaccount.com \
   DEADLINE_URL=<A が決めた期限サービスの URL> \
   ./scripts/deploy_worker.sh
   ```
   - ビルドは Cloud Build（A の Dockerfile、Python 3.11、固定した依存）。**初回は、10〜15分**かかることがある。
4. **確認**（下の §4）。
5. **（B）Scheduler の作成**（A の `POST /internal/maintenance` 追加後。決定済み）。

## 4. デプロイ後の確認

| 確認 | 方法 | 期待 |
|---|---|---|
| 起動 | `gcloud run services describe worker ... --format="value(status.latestReadyRevisionName)"` | 新しいリビジョンが、Ready で 100% の割り当て |
| 認証なしは拒否 | `curl -s -o /dev/null -w "%{http_code}" https://worker-122800925175.asia-northeast1.run.app/health` | 403（Cloud Run の IAM） |
| 起動エラーがない | `gcloud run services logs read worker --region asia-northeast1 --limit 30` | `Cloud mode requires ...` などのエラーがない |
| 通しの確認 | API のデプロイ後、3人で1ゲーム（A・フロントと共同）。段0の画像が作られ、段1へ進む | Firestore の `jobs` が `done` になる |

## 5. 切り戻し（問題が出たとき）

旧版（スタブ、`worker-00004-fdl`）に、すぐ戻せる。**データは変わらない。**

```bash
gcloud run services update-traffic worker --project gesture-relay-game --region asia-northeast1 \
  --to-revisions worker-00004-fdl=100
```

## 6. リスクと注意

| リスク | 対処 |
|---|---|
| `DEADLINE_URL` が未作成のサービスを指す | 期限のタスクが失敗し、Cloud Tasks が再試行する（最大3回）。ゲームの締切が動かない。**期限サービスを先に、または同時にデプロイする** |
| `iam.serviceAccountUser` が無い | タスクの作成が拒否される（`PERMISSION_DENIED`）。ログに出る。手順 2 を実施する |
| 旧 Worker（スタブ）が、Firestore に何も書かない | 置き換え後に、初めて実データが流れる。**最初は、1部屋だけで確認する** |
| AI の費用 | 1ゲームで、画像2枚＋文章。クレジットの範囲（残り ¥47,462）で、十分に収まる |
| Docker ビルドの失敗 | A の Dockerfile のビルドは、この環境では未確認（Docker なし）。Cloud Build のログで直す。旧版は、そのまま動き続ける |

## 7. 承認が要る操作（この手順書のうち）

| 操作 | 状態 |
|---|---|
| 手順 2（IAM: `iam.serviceAccountUser`） | 承認済みの #1 の範囲（API 実行 SA の分と合わせて、宛先が増えた旨を再確認） |
| 手順 3（本番デプロイ） | ⬜ 承認待ち（#3b） |
