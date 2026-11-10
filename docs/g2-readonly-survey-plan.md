# G2：クラウド現状調査の事前計画（未実行）

2026-11-08。基点：main `c8e2375`、PR #2 merged、PR #3/#4は未マージ。
**今回は計画だけ。Google Cloud/Firebaseへのログイン、実API、料金照会、実AI、秘密取得は一切実行していない。**
調べたのはローカルコード、GitHubの既存文書・PR、公開の公式ドキュメントだけ。公開ドキュメントは実プロジェクトの照会ではない。
文書中の「B報告」「ユーザー報告」はAの現状確認済みを意味しない。古い記録の不一致を推測で埋めない。

## 今夜のB記録との突合（実アクセスなし）

- 対象：main c8e2375 のpending-approvals.md、worker-redeploy-runbook.md、12e0498の変更記録。
- B報告ではtasks-invoker作成/Worker Invoker、マスターによるWorker runtime SAのactAs付与が済み。
  API SAのenqueue/actAs、deadline Invokerは未実施。Worker enqueueはEditorに含む「想定」とされ、実policy確認と区別する。
- Scheduler毎分は方針決定だけ。実作成は未実施。Aの保守HTTP入口は今夜の独立ブランチでローカル実装/検証したが、main/実Runには未配備。
- Web app登録はフロントの報告、Rules反映はB/マスターの報告。現在値のA照会はゼロ件。
- これらは過去の別担当に対する承認記録であり、今回Aのログイン/読取/設定変更の許可へ拡張しない。
- 次回のG2承認依頼では、Runtime SA・配送SA・service agent・配備者の区別、Worker/deadline両方のenqueue/actAs、
  Scheduler名義とdeadlineベースaudienceを調査票に含める。実値を得た後、変更承認をさらに別に取る。

## 実行前のゲート

1. 人間から「G2の読み取り専用調査」を別途明示承認してもらう。対象project、region、billing accountの範囲、調査者と既存の認証方式、閲覧可の情報と保存先を指定する。
2. 権限は下記のメタデータ読取に必要な既存権限のみ。権限不足ならその項目を未確認とし、ロール追加・SA作成・API有効化・ログイン設定変更で補わない。
3. 使う認証の選択/ログイン自体も今回は禁止。将来も秘密鍵/トークンの表示・抽出・保存、SAキー作成、サービスアカウントの偽装は調査に含めない。
4. 取得項目を先に限定し、環境変数の値、Secret Manager参照値、OAuth client secret、Web SDK key/config、ユーザー一覧、アプリの入力/動画/画像は取得しない。
5. 403/404/API無効/一覧空は別々に記録。403/404やCLIが返せないことから「存在しない」「安全」「料金ゼロ」と結論しない。ページングと対象regionの網羅も確認する。
6. G2は調査報告で終了。修正・作成・デプロイ・実AI・G3以降へ自動移行しない。read-only調査の承認を変更操作の承認に拡張しない。

## 項目別の調査票

### 1. Google Cloudプロジェクト

| 項目 | 計画 |
|---|---|
| 目的 | A/B/フロントが同じ実プロジェクトを指すか確認し、重複プロジェクトへの操作を防ぐ |
| 確認 | project ID/number、lifecycle、親階層の識別子、有効API（Firestore/Auth/Run/Tasks/Storage/Scheduler/Vertex/Rules）。全プロジェクトを探索しない |
| 必要な読取権限 | 対象へのresourcemanager.projects.get、serviceusage.services.get/list。例：対象範囲のBrowser/Service Usage Viewer、または必要permissionだけの既存custom role |
| 読取方法 | 承認後にprojects.describe、services.list --enabled。projectを毎回明示し、CLIの既定projectを変更しない |
| 現在の記録 | B文書はgesture-relay-game / number 122800925175を使用と報告 |
| 未確認 | Aによる現存/lifecycle/有効API/親階層の実照会は未実施 |
| 変更承認 | project作成/削除/移動、API有効化/無効化、設定変更は別途承認 |

### 2. Firestoreの存在・リージョン・モード

| 項目 | 計画 |
|---|---|
| 目的 | Aの保存先とデータベース前提を確認する |
| 確認 | database ID、location、FIRESTORE_NATIVE等のtype、edition、削除保護。データ/ドキュメント内容は読まない。Rulesの公開版は別にソースとの差分確認だけ |
| 必要な読取権限 | datastore.databases.list / datastore.databases.getMetadata。Rulesを読む場合はfirebaserules.releases.get/list、firebaserules.rulesets.get。データ読取ロールの付与は要求しない |
| 読取方法 | databases.list/describeのメタデータ、既存のRules release→rulesetを読む。Rulesソースに秘密がないか公開前に確認 |
| 現在の記録 | pending-approvals #4はBが(default)を東京/Native/Standardで作成済み、#9はマスター公開のFirestore RulesをBが一致確認したと報告 |
| 未確認 | 現在のDB・edition・公開Rules。#4に「未反映」も残るため#9の報告を現状断定に置き換えない |
| 変更承認 | DB作成、location/mode変更、Rules反映、データ変更/削除はすべて別途承認 |

### 3. Firebase Authentication

| 項目 | 計画 |
|---|---|
| 目的 | フロントの匿名ログインが本番で許可される前提を確認する |
| 確認 | プロジェクトのAuth初期化状態、匿名sign-inの有効/無効、承認済みドメイン。ユーザー/パスワード/ハッシュ/OAuth secretは対象外 |
| 必要な読取権限 | firebaseauth.configs.get（getSecret/getHashConfig/ユーザー読取は不要） |
| 読取方法 | Auth設定の表示、またはIdentity Toolkit projects.getConfigをフィールド限定で読む。OAuth provider詳細/secretは取得しない |
| 現在の記録 | Emulatorの匿名認証はローカル実証済み。公開文書に本番Authの現在値を示すA検証証拠はない |
| 未確認 | 実Authの存在・匿名設定・ドメイン。Emulator成功はその証拠にならない |
| 変更承認 | 初期化、provider/匿名設定、ドメイン追加、ユーザー操作は別途承認 |

### 4. Firebase Webアプリ登録

| 項目 | 計画 |
|---|---|
| 目的 | フロントが利用するWeb appの登録先と重複を確認する |
| 確認 | appId、表示名、状態、所属projectだけ。SDK config/apiKeyの値は取得しない |
| 必要な読取権限 | firebase.projects.get、firebase.clients.list/get。SDK key stringやsecret取得権限は使わない |
| 読取方法 | Firebase Management projects.webApps.listのページングを完了し、必要なメタデータだけ抽出する（getConfigは呼ばない） |
| 現在の記録 | #7は当時未登録と報告。その後PR #3のフロントAIがgesture-relay-game-web登録済み・本番設定はGit対象外と報告。Aはその設定値を取得していない。PR #3の.env.emulatorはダミー値 |
| 未確認 | 現在の登録/重複/対象appをAが実照会した証拠はない。過去の「No apps found」もフロント報告もAの現物確認に置き換えない |
| 変更承認 | 登録/削除、SDK設定値の配布、実フロントへの本番接続は別途承認 |

### 5. Cloud Run（API・Worker・期限サービス）

| 項目 | 計画 |
|---|---|
| 目的 | 各サービスの存在、実際の起動入口・接続・公開範囲を確認する |
| 確認 | region/name、revision/image、URL、実行SA、ingress、min/max instance、concurrency、timeout、Invoker IAM。環境変数はSERVICE_ROLE等の必要な非秘密項目の有無を人間が選別。全env/export yamlを収集しない |
| 必要な読取権限 | run.services.list/get、run.revisions.list/get、run.services.getIamPolicy。例run.viewerで不足するIAM policy読取は別に確認 |
| 読取方法 | services.list/describeを必要fieldsだけで取得し、IAM policyを別読取。URLを取得してもcurl/health/業務APIを呼ばない |
| 現在の記録 | Bは旧workerスタブ/AI_MODE=realの配備を報告。ユーザーはPR #2最終承認時に未デプロイを確認したと報告。API/deadlineの実URLはA未取得 |
| 未確認 | 最新の全サービスと各入口。配備済みコードがapi.workerかLogSinkか、CPU/ゼロ台、SA/URL/IAMは要実照合 |
| 変更承認 | build/deploy、サービス作成、traffic、env、IAM、ingress/min-instanceの変更、URLへの試験リクエストは別途承認 |

### 6. Cloud Tasks

| 項目 | 計画 |
|---|---|
| 目的 | enqueue先と再配送条件がA/Bの復旧設計に合うか確認する |
| 確認 | region/queue、state、retry/rate limits、配送先設定/権限。task本文やユーザー入力は取得しない |
| 必要な読取権限 | cloudtasks.queues.list/get、必要ならqueues.getIamPolicy。task fullView権限は不要。例cloudtasks.viewerは必要以上のtask読取を含み得るためmetadata限定の既存権限を優先 |
| 読取方法 | queues.list/describe。IAMはpolicy読取のみ。tasks.create/run/purge/pause/resumeは実行しない |
| 現在の記録 | B報告：gesture-jobs、asia-northeast1、最大試行3、間隔5〜60秒、同時実行4。古いコメントには10もある |
| 未確認 | 現在の値、送信SAの権限、正しいWorker/deadline audience。queueの空き/存在と業務配送成功を混同しない |
| 変更承認 | queueの作成/更新、task登録/再実行/削除、IAM変更は別途承認 |

### 7. Cloud Storageと24時間削除

| 項目 | 計画 |
|---|---|
| 目的 | 非公開アセットと画像/録画の保存期間が決定どおりか確認する |
| 確認 | bucket/location、uniform bucket-level access、public access prevention、lifecycleのDelete/age/条件、versioning/soft delete、IAM。ファイル名一覧・画像/録画本体は取得しない |
| 必要な読取権限 | storage.buckets.list/get、storage.buckets.getIamPolicy。storage.objects.get/listは不要 |
| 読取方法 | buckets.describeのメタデータとIAM。lifecycleが画像/録画双方を対象にするか確認し、時刻どおりの削除を推測しない |
| 現在の記録 | gesture-relay-game-assets、東京/非公開、全体24hのB報告。Aはleave/startで録画のみ削除、画像はlifecycleに任せる |
| 未確認 | 実lifecycle/例外条件、soft-deleteとversioningによる保持/費用、実IAM。Emulatorの手動削除テストは実設定の証拠ではない |
| 変更承認 | bucket作成、lifecycle/保持/公開設定/IAM/データ操作は別途承認 |

### 8. サービスアカウントとIAM

| 項目 | 計画 |
|---|---|
| 目的 | API実行SA、Worker/期限SA、Tasks配送SAの役割と不足/過剰権限を確認する |
| 確認 | SAメタデータとproject/Run/SA policyのbindings・conditions。APIのTasks Enqueuer、配送SAに対するactAs、配送SAのWorker/期限Invokerを区別。キー/トークンの取得は対象外 |
| 必要な読取権限 | iam.serviceAccounts.list/get/getIamPolicy、resourcemanager.projects.getIamPolicy、各resourceのgetIamPolicy。既存の限定security-review権限を使用 |
| 読取方法 | SA一覧/describeと対象ごとのget-iam-policy。特定SA自身のpolicyだけで、そのSAが他resourceで持つ全権限を結論しない |
| 現在の記録 | #1はtasks-invoker作成/Worker Invoker付与をBが実施済みと報告。API実行SAと期限Invoker/enqueue/actAsは未実施と報告。confirmation-itemsには未作成も残る |
| 未確認 | 実在、API/Worker/deadlineの実行SA名、実policy/conditions/継承。記録の食い違いは実値と時刻で解決する |
| 変更承認 | SA/キー作成、role付与/削除、custom role、token生成/偽装は別途承認。今回も将来G2もsecret取得はしない |

### 9. Cloud Scheduler

| 項目 | 計画 |
|---|---|
| 目的 | ゼロ台時の保守呼出の仕組みと誤った本番起動経路を確認する |
| 確認 | jobの存在、region、schedule/timezone/state、HTTP method/宛先のorigin+path、OIDC SA/audience。HTTP body/headersの秘密値は取得しない |
| 必要な読取権限 | cloudscheduler.jobs.list/get（例cloudscheduler.viewer。ただし取得fieldsを限定） |
| 読取方法 | jobs.list/describeのmetadataだけ。run/resume/create/patchは呼ばない |
| 現在の記録 | main3ce0242の#2は1分おきSchedulerを決定、実作成未実施と報告。AのPOST /internal/maintenance追加が前提と記載 |
| 未確認 | 現在のjob、保守入口の配備、対象SA/audience、失敗/リトライ状態。mainには独立maintenance HTTP入口なし。Aの今夜の別ブランチだけにローカル実装済みで、実Runに存在する証拠ではない |
| 変更承認 | 保守入口の実装は別のローカル作業として協議。job/SA/IAM/稼働/課金設定/デプロイは別途承認 |

### 10. Vertex AI

| 項目 | 計画 |
|---|---|
| 目的 | Bのモデル/region/実行SAと利用設定を照合する |
| 確認 | Vertex API有効状態、実行SAのrole、location、設定モデル名、quotaのmetadata。推論・embedding・画像生成・モデルdeployをしない |
| 必要な読取権限 | serviceusage.services.get/list、必要範囲のserviceusage.quotas.get、IAM policy読取。利用量metricsを追加する場合はmonitoring.timeSeries.listを別承認 |
| 読取方法 | 有効サービス/既存quota画面と配備metadataを読む。serverlessモデル利用はendpoint一覧が空でも否定できない。予測/生成APIで動作確認しない |
| 現在の記録 | B報告はVertex global、PNG、429対策と別モデル/region fallback。コードはmainに統合済み |
| 未確認 | 実際の有効API、モデル利用権/region/quota、実行SA、実使用量。B実験の過去結果を現在の可用性と見なさない |
| 変更承認 | API有効化、quota変更、実AI、モデル/regionの配備変更、有料API切替は別途承認 |

### 11. 請求先

| 項目 | 計画 |
|---|---|
| 目的 | 対象projectの課金先と請求有効状態を限定的に確認する |
| 確認 | projectへのbilling account関連付け、有効状態。決済手段/住所/請求書/他project情報は取得しない |
| 必要な読取権限 | projectの課金関連付けの読取はresourcemanager.projects.get、口座メタデータには必要範囲のbilling.accounts.get。projects.getBillingInfoはAPIメソッド名でありIAM permission名ではない。Billing Account Viewer等は口座scopeで別許可が必要。project Viewerだけで費用閲覧を保証しない |
| 読取方法 | billing.projects.describeと人間が許可したaccountのメタデータ。支払情報を表示する画面へ進まない |
| 現在の記録 | 使うproject ID以外、Aが検証したbilling account情報はない |
| 未確認 | account ID、課金有効状態、調査者の可視範囲、クレジット/請求の扱い |
| 変更承認 | 課金先関連付け、plan/支払方法変更、クレジット購入は別途承認 |

### 12. 現在の費用

| 項目 | 計画 |
|---|---|
| 目的 | デモ実施の前提となる実費/クレジット/更新遅延を把握する |
| 確認 | 明示した日付範囲・timezone・projectの費用、service別内訳、gross/credits/net、表示通貨、データ更新時刻。料金表と実請求を区別 |
| 必要な読取権限 | account scopeのbilling.accounts.getSpendingInformation、または許可されたproject scopeの費用閲覧。例Billing Account Viewer/限定custom role。既存の権限を使い、付与はしない |
| 読取方法 | 承認後に既存Billing Reportsの表示だけ。集計条件を記録し、報告書の保存や新規exportを作らない。BigQuery課金クエリ/新規exportは実行しない |
| 現在の記録 | Aによる現在費用の確認はゼロ件。Bの料金見積・無料枠/クレジットの説明は未検証の報告 |
| 未確認 | 実費・クレジット残高・将来料金。金額を推測しない。未集計/遅延を0円と解釈しない |
| 変更承認 | 費用表示自体を含むG2読取の事前承認が必要。export/有料照会/購入/課金変更は別承認 |

### 13. 予算通知

| 項目 | 計画 |
|---|---|
| 目的 | 予算と通知設定が存在し、対象projectに適用されるか確認する |
| 確認 | budgetの対象filter、金額/通貨、閾値、通知先の種類、通知先の有効性を人間が確認。通知先個人情報は出力しない。通知と支出強制停止を混同しない |
| 必要な読取権限 | billing.budgets.list/get、対象accountの費用閲覧権限。例Billing Account Viewerまたは限定custom role |
| 読取方法 | 既存Budgetの一覧/表示。メール送信テスト、Pub/Sub publish、budget更新はしない |
| 現在の記録 | 予算/通知に関するAの確認済み情報なし |
| 未確認 | 予算の存在・金額・filter・通知先。調査だけで通知可能と保証しない |
| 変更承認 | 予算/閾値/通知先/PubSub/支出制限の作成・変更は別途承認 |

### 14. GitHub Webhooks・Installed Apps・デプロイ連携

| 項目 | 計画 |
|---|---|
| 目的 | main/PR/pushで外部deploy/Cloud操作が起動する経路を把握する |
| 確認 | repository/org hooksの有効状態・イベント・宛先ホスト、Installed Appsの対象repo/権限/イベント、Actions/workflow、外部CI/Cloud Build等の連携。hook secret/署名鍵/tokenは取得しない |
| 必要な読取権限 | GitHub repo管理者の設定閲覧、API利用時はWebhooks(read)。App/organization設定はそれぞれ管理者による確認。GCPトリガーは承認されたread-only範囲で別照会 |
| 読取方法 | 人間がSettings→Webhooks/Installed GitHub Appsと外部CI設定を閲覧。APIはlist hooksの必要fieldだけ。現在のコネクターが未対応なら管理者の確認記録を受け取り、権限を拡大しない |
| 現在の記録 | G0時にrepo内workflowは見つからず、BがCloud側トリガーなしを報告。Aのhook/App照会は未対応・権限不足。PR #2はその後ユーザーの最終明示承認でコードだけmerge済み |
| 未確認 | 現在のrepo/org hooks、Installed Apps、外部CIとdeploy連携。単一の接続済みGitHub App一覧や「現在未デプロイ」は全経路不存在の証明に使わない |
| 変更承認 | hook/Appの追加/削除/無効化、Actions/CI/Cloud Build/Hosting設定、権限拡張、試験pushによるdeploy起動は別途承認 |

## 将来の読取コマンド例（すべて未実行）

承認後、既存の承認済みセッションと明示project/regionを使う例。以下を今回コピーして実行しない。
CLIのインストール/ログイン/API有効化も本計画の実行前提として勝手に行わない。
全出力ではなく必要fieldsを選び、env/credentials/bodiesを含むdescribe全体やexport YAMLを保存しない。

```bash
# G2承認後のみ。これらの変数は識別子であり秘密ではない。
SURVEY_PROJECT_ID='gesture-relay-game'
SURVEY_REGION='asia-northeast1'
gcloud projects describe "$SURVEY_PROJECT_ID" --format='json(projectId,projectNumber,lifecycleState)'
gcloud services list --enabled --project "$SURVEY_PROJECT_ID" --format='value(config.name)'
gcloud firestore databases list --project "$SURVEY_PROJECT_ID" --format='json(name,locationId,type,databaseEdition)'
gcloud firestore databases describe --database='(default)' --project "$SURVEY_PROJECT_ID" --format='json(name,locationId,type,databaseEdition)'
gcloud run services list --project "$SURVEY_PROJECT_ID" --region "$SURVEY_REGION" --format='table(metadata.name,status.url)'
gcloud run services describe '<SERVICE>' --project "$SURVEY_PROJECT_ID" --region "$SURVEY_REGION" --format='json(metadata.name,status.url,status.latestReadyRevisionName,spec.template.spec.serviceAccountName)'
gcloud tasks queues list --project "$SURVEY_PROJECT_ID" --location "$SURVEY_REGION" --format='table(name,state)'
gcloud tasks queues describe gesture-jobs --project "$SURVEY_PROJECT_ID" --location "$SURVEY_REGION" --format='json(name,state,rateLimits,retryConfig)'
gcloud storage buckets describe 'gs://gesture-relay-game-assets' --format='json(name,location,uniform_bucket_level_access,public_access_prevention,lifecycle_config,versioning_enabled,soft_delete_policy)'
gcloud iam service-accounts list --project "$SURVEY_PROJECT_ID" --format='table(email,disabled)'
gcloud projects get-iam-policy "$SURVEY_PROJECT_ID" --format='json(bindings)'
gcloud iam service-accounts get-iam-policy '<SA_EMAIL>' --project "$SURVEY_PROJECT_ID" --format='json(bindings)'
gcloud run services get-iam-policy '<SERVICE>' --project "$SURVEY_PROJECT_ID" --region "$SURVEY_REGION" --format='json(bindings)'
gcloud scheduler jobs list --project "$SURVEY_PROJECT_ID" --location "$SURVEY_REGION" --format='table(name,state,schedule,timeZone)'
gcloud billing projects describe "$SURVEY_PROJECT_ID" --format='json(projectId,billingAccountName,billingEnabled)'
```

- regionを東京だけに固定して全サービス不存在と結論しない。承認対象regionリストで同じlistを繰り返す。
- Storage表示fieldはCLIの世代で異なる場合がある。空fieldを「設定なし」と解釈せず、承認後に公式reference/metadata schemaへ照合して必要fieldだけを再取得する。
- Auth/Web appは上記の設定限定API/Consoleを使う。Web app SDK getConfigやAuth sign-inは調査に含めない。
- IAM getIamPolicyのRESTがPOSTであることもあるが、既存policyを読む操作。HTTP verbだけで変更/読取を決めない。
- billing account ID取得後の予算/費用閲覧は口座scopeの個別承認が必要。他projectの費用や決済情報を見ない。

### 変更操作は別フェーズ（実行例は作らない）

create/update/delete/deploy、services enable、set/add/remove-iam-policy-binding、Auth provider/domain更新、
task create/run、scheduler create/run/resume、AI generate/predict/embed、budget create/update、billing link、
Firestore/Storage data read/export、secret access、token/key生成や表示は上記のmetadata調査に含まない。
検出した不足を自動修復しない。G2報告で必要性・影響・費用・戻し方を提示してから人間がG3以降を承認する。

## 記録の矛盾と証拠フォーマット

現時点の矛盾：#1のSA作成済み報告とconfirmation-itemsの未作成、#4のRules未反映と#9の反映済み、
旧Worker配備済み報告と後日のユーザー未デプロイ確認。最新の現物をまだ読んでいないため勝手に一方を削除しない。
「Cloud Schedulerを採用する決定」と「Schedulerの実作成」は別。保守HTTP入口が存在しないというコード上の事実も分ける。

将来の各結果は `対象ID / 時刻(JST・UTC) / 実行者 / 読取方法 / scope・filters / 確認値 / 出典 / 未確認理由 / 次の変更承認` を記録。
費用/個人識別/内部IAM等の生データはGitHubへ保存しない。人間が許可した限定保存先へ置き、共有文書にはredacted summaryと確認時刻だけを書く。

## 人間から必要な承認のひな型

> G2の読み取り専用調査を、指定project・region・billing account・期間と既存調査者で許可する。
> メタデータ、Auth設定の匿名有効/ドメイン、Web app一覧、IAM、予算/費用の指定範囲を閲覧してよい。
> 本番ログイン/使用する既存認証方式・権限は人間が指定する。必要な権限の追加は別承認。
> secret/認証情報/ユーザー/アセット本体を取得せず、実AI・Cloud Run URL呼出・作成/変更/デプロイ・課金変更はしない。
> 403/API無効/不足があれば調査結果として止め、G3以降へ進まない。

このひな型は承認を受けた記録ではない。返答がないこと、過去の別担当への権限付与や作成承認、GitHub上の記述を今回の実アクセス許可に使わない。

## 公開の公式資料（計画の根拠、実project未照会）

- [Firebase IAM permissions](https://firebase.google.com/docs/projects/iam/permissions) / [WebApps list](https://firebase.google.com/docs/reference/firebase-management/rest/v1beta1/projects.webApps/list)
- [Firestore metadata/IAM](https://docs.cloud.google.com/datastore/docs/access/iam) / [database management](https://docs.cloud.google.com/datastore/docs/manage-databases)
- [Identity Toolkit API](https://docs.cloud.google.com/identity-platform/docs/reference/rest) / [Config schema](https://docs.cloud.google.com/identity-platform/docs/reference/rest/v2/Config)
- [Cloud Run describe](https://docs.cloud.google.com/sdk/gcloud/reference/run/services/describe) / [Run IAM](https://docs.cloud.google.com/run/docs/securing/managing-access)
- [Tasks permissions](https://docs.cloud.google.com/iam/docs/roles-permissions/cloudtasks) / [Scheduler permissions](https://docs.cloud.google.com/scheduler/docs/access-control)
- [Storage metadata permissions](https://docs.cloud.google.com/storage/docs/access-control/iam-permissions)
- [Service accounts/IAM](https://docs.cloud.google.com/iam/docs/roles-permissions/iam) / [SA getIamPolicy](https://docs.cloud.google.com/iam/docs/reference/rest/v1/projects.serviceAccounts/getIamPolicy)
- [Service Usage Viewer](https://docs.cloud.google.com/iam/docs/roles-permissions/serviceusage)
- [Billing access](https://docs.cloud.google.com/billing/docs/how-to/billing-access) / [Budget permissions](https://docs.cloud.google.com/billing/docs/how-to/budgets) / [custom Billing permissions](https://docs.cloud.google.com/billing/docs/how-to/custom-roles)
- [GitHub webhook read permission](https://docs.github.com/en/rest/repos/webhooks)
