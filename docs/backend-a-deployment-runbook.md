# A：API・deadline/保守の本番準備手順（未実行）

> 2026-11-09更新：最新main追従と新規検証、Bの実行SA・配備報告、現在の残条件は [A再開状況](a-resume-status.md) を参照。以下の未確定/レビュー待ち等は当時の記録です。

2026-11-08、コード基点main c8e2375 + PR #6。クラウド読取・ログイン・build/push・配備・IAM・課金は一切実行していない。
以下の手順・コマンドは将来の変更案であり、実行の承認を意味しない。11/10 17:00に向けた準備資料。

## 入口・責任境界

| 用途 | 起動 | 入口 | 呼出者/認証 |
|---|---|---|---|
| API | SERVICE_ROLE=api → api.main:app | 14本の/api/** | 端末のFirebase ID token。内部URLは存在しない |
| deadline + 保守 | SERVICE_ROLE=deadlines → api.internal:app | /internal/deadlines、/internal/maintenance | Run IAM + Google OIDC。aud=deadlineのベースURL、email=TASKS_SERVICE_ACCOUNT、email_verified=true |
| B Worker（変更しない） | SERVICE_ROLE=worker → api.worker:app | /tasks/run（/internal/jobs互換） | Run IAM + Google OIDC。aud=WorkerのベースURL、同じ配送SA |

保守入口はAのprivate appに明示的に追加。Worker/main.py、B handler/jobs/AI、JobPayload/Resultは変更しない。
maintenance_endpointの指定はAのcreate_app内部引数だけで、共有Settingsに新項目は足さない。

## 1回の保守処理

POST /internal/maintenance、body不要。成功200 `{"accepted":true}`。
dispatch_outbox → recover_job_progress → recover_job_execution → cleanup を順に1巡。
AIを直接呼ばず、queue/SA/Schedulerを作成しない。期限の時刻判定は既存deadline taskが担う。
`write_job_result → advance_step`、transactionと永続outboxを維持する。
重複/並行呼出を許容し、task名/出所revision/advance_pending等で再確定を防ぐ。

- このdeadline構成ではbackground loopを起動しない。API/Workerの従来の5秒loopは維持。
- 未認証/誤SAは401。未処理の例外は共通INTERNAL/500で、Schedulerの承認済みretry設定に委ねる。
- 個別outbox項目の失敗を既存処理が捕捉した場合、未処理を永続化して200となり得る。
  200は全outbox消化の保証ではない。次のcronで再試行し、運用ではoutbox滞留と失敗ログも確認する。
- Cloud runtimeのpassは専用子プロセスで実行し、開始後150秒のsubprocess.run timeoutでkill/reapする。
  timeout/異常終了は500とし永続outboxから再試行。同一instanceでの重複起動は500で再配送に委ねる。
  Runひな型は180秒へ変更し、Scheduler HTTPの既定180秒と照合する案。
  local/emulatorはMemoryTasksを失わないため従来の同一processで実行する。
- 1 passは1 transactionを意味しない。子の初期化も時間枠内だが、OSのprocess生成やRun cold startは別に時間を要する。
  実Cloud全体での3分未満は未測定。SDKの強制停止/commit済みack消失の実環境確認を別承認後に行う。
  詳細：[保守時間枠の検証](maintenance-time-budget.md)。

## 必須環境変数・設定

| 項目 | API | deadline/保守 | 補足 |
|---|---|---|---|
| SERVICE_ROLE | api | deadlines | YAMLの明示uvicorn argsも同じ入口を指す |
| PORT | 8080 | 8080 | imageは非root、proxy headers無効 |
| RUNTIME_MODE | cloud | cloud | **承認後のみ** |
| ENABLE_CLOUD | true | true | ひな型はfalseで安全に起動拒否。今回は変更しない |
| AI_MODE | mock | mock | AはAI非実行。Bの実AI設定は別担当・別承認 |
| PROJECT_ID | 承認対象ID | 同一 | demo-既定値を実環境へ流用しない |
| BUCKET_NAME | 非公開の承認済bucket | 同一 | A runtimeがGoogleBlobsを選択。STORAGE_MODE変更に依存しない |
| TASKS_LOCATION / TASKS_QUEUE | 既存queueのregion/name | 同一 | B報告は東京/gesture-jobs。実値未照会 |
| WORKER_URL | https://Workerベース/tasks/run | 同一 | 実際のRun URL確定後。URLを推測しない |
| DEADLINE_URL | https://deadlineベース/internal/deadlines | 同一 | 保守URLと混同しない |
| TASKS_SERVICE_ACCOUNT | 許可された配送SA email | 同一 | 現コードは許可email1個。新SA追加は契約調整が必要 |
| INTERNAL_AUDIENCE | deadlineベース（runtime構築に必要、公開APIでは検証口なし） | deadlineベース | WorkerではWorkerベース。path/query/trailing slashを含めず一致させる |
| CORS_ORIGINS | 同一originなら[] | [] | 別originの許可追加はフロントと確認 |
| DEADLINE_GRACE_S / DROPOUT_AFTER_S | 現設定5/15を維持 | 同一 | 秒数変更は人間判断。今夜独断で変更しない |

Firestore config/gameのtext_seconds/countdown_seconds/record_secondsはゲーム開始時snapshot。
10秒countdownはローカル検証だけ。実configの採用値・作成/変更は別途承認。
Cloud modeにEmulator用環境変数を残すと起動拒否する。ADCは将来Run runtime SAのみで、鍵ファイルは作らない。
API/期限サービスに実AIキー/Secret Manager権限を与えない。

## IAMとサービスアカウントの確認表（付与はしていない）

| 身元 | 必要な境界/候補permission | 実行前の確認 |
|---|---|---|
| API runtime SA | Firestore read/write（datastore.user候補）、bucket限定objects get/create/delete/list等、queue限定cloudtasks.tasks.create、配送SAへのiam.serviceAccounts.actAs、firebaseauth.users.get（check_revokedのため） | rolesは人間が最小権限でレビュー。Editor/Owner前提にしない |
| deadline runtime SA | Firestore、同bucketのcleanup、queueへのenqueue、配送SAへのactAs | 進行復旧が次のtaskを登録するため、受信だけの権限では不足 |
| Worker runtime SA | B管理のAI権限 + 永続IO/Firestore/Storage + enqueue/actAs | advance_step後の配送で必要。BのEditor前提記録をAの実確認に置き換えない |
| tasks-invoker（配送名義） | WorkerとdeadlineのRun Invokerのみ | runtime SAと区別。FirestoreやAI権限は配送名義には不要 |
| Scheduler jobの名義 | 現案はtasks-invokerを共有、deadline Invoker | job自身のaudをdeadlineベースに明示。別SAなら現コードの許可emailと先に調整 |
| Cloud Tasks/Scheduler service agent | それぞれの既存serviceAgent roleでOIDC token発行 | job名義にservice agentを指定しない。生成/付与/有効化は別承認 |
| 配備者/Scheduler設定者 | 対象resourceの配備/設定権限と指定runtime/job SAへのactAs | アプリruntime権限と混同しない。今回はログイン・権限取得もしない |

## Bの承認記録との照合（報告ベース、A未照会）

- pending-approvals #1：tasks-invoker作成/Worker InvokerはB実施報告。
  12e0498ではマスターがWorker runtime SAへtasks-invokerのService Account Userを付与しBが確認と報告。
  API SAのenqueuer/actAs、deadline Invokerは未実施と記録。
- Workerのenqueueは既定Compute SAのEditorに含む想定とB runbookに記載。Aは実policyを確認しておらず、想定を権限保証に使わない。
- #2のScheduler毎分は採用決定。実job作成/稼働承認とは別。保守入口はこのAブランチでローカル実装、main/Run未配備。
- #4と#9のRules反映記述、古いWeb app未登録とフロントの登録済み報告、古いSA未作成記録は
  G2で時刻/実値を照合する。過去文書を削除して確認済みに見せない。

## 承認後の配備順序（今回は未実行）

1. G2読取の対象・権限・期間・保存先を人間が承認し、既存設定を限定照会。結果を共有して変更承認を別に得る。
2. PRを個別承認/mergeした確定コード、image digest、reviewed manifest、旧revision/trafficを記録。
   image build/registry push、SA/IAM、API有効化、Run/Hosting/Scheduler変更をそれぞれ承認対象に含める。
3. Worker/期限の実URLとruntime/job SAを確定。未作成なら別途承認した**非公開・local/DenyInternalAuthのbootstrap revision**で
   URLだけ確定する案を人間と確認。bootstrapを公開しない。URL未確定のまま本番設定を適用しない。
4. 非公開deadlineをreviewed imageで配備。manifestの必須設定とENABLE_CLOUDを承認後に設定。
   IAMの未認証拒否、誤aud/SA拒否、正しいOIDCの1 pass、ログ/永続復旧を承認した検証環境で確認。
5. APIを配備しFirebase ID token・権限/アセット/14 APIを確認。Hosting経由で呼ぶ公開APIのRun入口公開/IAM変更は
   人間が別承認する。内部サービスは公開しない。公開APIもアプリのFirebase認証を必須とする。
6. Bが承認済みWorker入口とTasksを照合し、SchedulerをPOST/deadline/internal/maintenance・毎分・OIDCで設定する。
   既定aud（path付きURI）任せにせずベースURLを明示。Cloud Tasksは既存アダプターが各URLのoriginをaudにする。
7. フロント担当がHosting rewriteをレビューして承認後に配備。匿名Auth/各ドメインもG2で必要性を調査し、別承認して設定。
8. 承認された範囲で実3人テスト。実AIを使う場合はさらに明示承認が必要。成功した範囲と未検証を分けて報告。

### 将来の変更コマンド例（**未実行**）

```bash
# 変更操作。人間の個別承認後、値をレビュー済みmanifestへ反映してからのみ。
gcloud run services replace '<REVIEWED_DEADLINE_MANIFEST>' --project '<PROJECT>' --region '<REGION>'
gcloud run services replace '<REVIEWED_API_MANIFEST>' --project '<PROJECT>' --region '<REGION>'
```

IAM/SA作成・Scheduler作成・Hosting deployのコマンドはB/フロントの承認済み手順と統一してから用意する。
ここにsecret/token取得コマンド、実projectへの試験curl、SA key作成は含めない。

## ロールバック（変更操作・別承認、未実行）

各サービスの旧revision/digest/非秘密設定/traffic、Hosting release、Scheduler設定を配備前に記録する。
旧revisionが存在しない初回配備ではtraffic rollbackはできない。bootstrap等の退避先を先に承認する。

```bash
# 変更操作。既知の安全なrevisionを確認し、人間がrollbackを承認した場合のみ。
gcloud run services update-traffic '<SERVICE>' --to-revisions='<OLD_REVISION>=100' --project '<PROJECT>' --region '<REGION>'
```

- Schedulerの先行停止/戻し方、Hosting releaseの戻し、Tasks配送先の切替はB/フロントと順番を確認。
  trafficだけ戻して既存task payload/targetやenvが戻るとは扱わない。
- データの削除/巻き戻しはしない。既存outbox/Job revisionを保持。設定を戻す場合もsnapshot済み進行への影響を確認。
- IAMを一括で緩めたり取り消したりしない。認証不備なら公開範囲を人間と閉じる手順を別承認する。
- maintenanceの200だけを成功指標にせず、未処理outbox・失敗ログ・期限task配送と一巡を確認する。

## Hosting/Authのフロント確認票

infra/hosting.json.exampleの順序：/api/** → API Run（serviceId/region明示）、最後に ** → /index.html。
/internal/**・Worker・deadline・maintenanceはHostingへrewriteしない。
フロントのVITE_API_BASE_URLは同一originなら空文字。Authorization/multipart/asset Content-Type/Cache-Controlを将来実経路で確認。
Hosting経由は60秒制限があるためAIは非同期202のまま。API Run入口の公開方針は非公開Worker/deadlineと分けて承認する。
pinTagはHostingとRunのrollbackを結び付けるため今回は無断追加しない。
Auth匿名有効、使用project/app、Hosting/preview/custom domainと必要な承認済みドメインを確認する。
ドメイン追加が匿名認証だけで必要かも調べ、警告を見ただけで設定しない。.env.productionは取得/Pushしない。

## 公式資料（公開文書のみ参照、実Cloud未照会）

- [Scheduler OIDCとservice agent](https://docs.cloud.google.com/scheduler/docs/http-target-auth)
- [Cloud Run Scheduler連携](https://docs.cloud.google.com/run/docs/triggering/using-scheduler)
- [Cloud Tasks HTTP/OIDC](https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks)
- [Hosting/Cloud Runの公開入口・rewrite・60秒制限](https://firebase.google.com/docs/hosting/cloud-run)
