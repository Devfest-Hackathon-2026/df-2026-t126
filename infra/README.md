# インフラ設定案（未適用・実環境未検証）

レビュー用雛形です。実プロジェクト・認証情報・IAMを操作していません。
本番適用、API有効化、課金、IAM変更にはユーザーの新たな許可が必要です。
今夜のG1/A準備ブランチへの通常Push・Draft PR作成は許可済みで、mainマージはPRごとの明示承認待ちです。
`ENABLE_CLOUD=false` のままでは起動を拒否します。実接続を承認してから設定してください。

## A/Bの分担

- A: API用Run、期限受信用の非公開Run、Firestore/Storage Rules、Hosting接続案。
- B: AI Worker用Run、Cloud Tasksキューと再試行、AIキー/Secret Manager、録画・生成画像の24時間ライフサイクル設定。
- Aは既存キューへの配送アダプターのみ実装。キュー作成処理はありません。
- Hostingのビルド出力・リージョン・公開URLはフロントと確認します。

## 適用前の確認

1. プロジェクト、リージョン、非公開バケット、サービスURL、実行SAを確定。
2. API・期限受信SAのFirestore/Storage・Tasks Enqueuer権限をレビュー。APIはAIキーを取得しない。
3. Tasks配送SAに宛先Run Invoker、作成側に当該SAの利用権限を付与する案をレビュー。
4. 期限受信Runにunauthenticatedアクセスを許可しない。
   `api.main:app` には `/internal` が登録されない。
5. OIDC audienceはサービスのベースURL。アプリもaudienceとSA emailを検証。
6. `config/game` に `text_seconds`、`countdown_seconds`、`record_seconds` を作成。
   Cloud modeは未設定のゲーム開始を拒否する。ローカル60/3/5秒は仮値。
7. Bのwrite_job_resultとadvance_stepを結合検証。詳細はintegration文書参照。
8. 最新mainの決定に従い録画・生成画像を作成から24時間で自動削除。Bはバケット全体に設定済みと報告。
   Aでは実設定を取得していない。leave/startは録画だけ個別削除、画像はlifecycleに任せる。

Dockerfileは非rootユーザー・8080ポートで起動します。
ローカル実行時は `RUNTIME_MODE=local` を明示してください。
Docker daemonが停止していたため、このセッションではイメージbuild/runは未検証です。

## Scheduler保守入口（ローカル実装、未配備）

`api.internal:app` は期限と `POST /internal/maintenance` を受ける非公開サービス。
保守はOIDC検証後に1 passだけ実行し、この構成では5秒のbackground loopを起動しない。
API/Workerの従来loopは維持。APIおよびWorker構成にこの保守HTTP入口は登録しない。
Schedulerは `INTERNAL_AUDIENCE` にdeadlineのベースURLを明示し、既存 `TASKS_SERVICE_ACCOUNT` を使う案。
別Scheduler SAを許可する設定は未追加で、Bとの調整と別途人間承認が必要。
詳細は [Aの配備・ロールバック手順](../docs/backend-a-deployment-runbook.md)。今回はすべて未適用。

## 公式SDK資料

- [Firestore transactions](https://firebase.google.com/docs/firestore/manage-data/transactions)
- [Firebase Admin token verification](https://firebase.google.com/docs/reference/admin/python/firebase_admin.auth)
- [Cloud Tasks HTTP/OIDC delivery](https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks)

外部GitHubプロジェクトの実装コードはコピーしていません。
