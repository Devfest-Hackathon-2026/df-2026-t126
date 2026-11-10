# バックエンドA 開発進捗

> 2026-11-09更新：最新main追従と新規検証、Bの実行SA・配備報告、現在の残条件は [A再開状況](a-resume-status.md) を参照。以下の未確定/レビュー待ち等は当時の記録です。

## 最新：PR #6承認済みmerge・#3再検証・保守時間枠（2026-11-08）

- 人間の#6単独承認に基づきmain bedcc62/head ef3bbe2/Ready/cleanを直前照合し、通常merge成功。
  main **150df957f6aa11cb75e8d5b383791577a7f0e23e**、PR #6 merged/closedと両parentを確認。
  codex/g1-validation-handoffはef3bbe2で保持。#3/#4/#7 merge/base変更、実Cloud操作は未実行。
- #3 frontend93717e1 + 新mainの隔離merge a36ea00は競合なし。
  新規Emulator142 passed（31.16秒）/Rules5、frontend14・lint/tsc/build、14 API/B MockAI/3人一巡成功。
  frontend所有ブランチは変更せず、担当へ新main取込と新head指定を依頼。新head後の再確認・#3個別承認待ち。
- #7にCloud child150秒上限/kill-reap/instance内重複起動拒否を実装。Run例180秒、local/emulatorはin-process維持。
  保守19ケース成功。実Cloudでのcold startを含む3分未満は未保証。詳細maintenance-time-budget.md。
- 追加検証で既存同時提出競合が1 failed/160 passed。独立Firestore入場制御修正を併用すると
  Emulator161/Rules5と3人一巡成功（12.33秒）。この161件は修正併用の結果で#7単独の成功ではない。
  Transaction修正は別Draft PR #8（codex/firestore-local-admission、f7b7b40）で分離。
  修正単体もEmulator142（9.97秒）/Rules5/14 API/B MockAI/3人成功。#3承認前の既知リスクとして共有する。
- 次回：最新main/PR #3 head/新しい修正PRの状態を取得し、対象treeと未検証を確認する。
  #7 baseは既存のまま、変更/mergeは行わない。G2/配備/実AI/課金には自動移行しない。

## 最新：今夜の保守API・G1統合準備（2026-11-08）

- 独立ブランチcodex/backend-a-maintenance（#6 ef3bbe2起点）。main c8e2375/フロントheadは取得時から不変。
  作業中に#3 93717e1/#4 47fc72eが到着。新headで再検証し、#6→#3→#4の依存とPRごとの承認待ちをbackend-a-night-statusへ記録。
- 実装済み：api.internal:app限定POST /internal/maintenance。Google OIDCの既存aud/email検証後に1 pass。
  dedicated deadline構成のbackground loopは停止し、API/Workerは既存loopのまま。公共14 API/共有型/B実装は不変。
- 新規13テスト：未認証/誤SA拒否、1 pass、並行/重複、保存済みWorker結果・実行receipt・配送失敗・録画cleanupの復旧。
  offline152 passed/3 skipped、Emulator155 passed（31.34秒）/Rules5 passed、現行front14 API/B MockAI/3人一巡が新規成功。
- API/deadline runbook、IAM/OIDC/Tasks境界、Hosting/Auth確認票、rollback、B承認記録に照合したG2計画を保存。
  YAMLはENABLE_CLOUD=falseの未適用案。実クラウドの読取/ログイン/デプロイ/秘密取得/実AIは一切未実行。
- B/フロントへGitHubで調整依頼。返信待ちの共有変更は確定しない。各PRのmainマージとG2実調査は別途人間承認。
- G1/#6単独の新規再検証：Emulator142 passed（22.53秒）/Rules5、93717e1/47fc72eの各14 API/B MockAI/3人一巡成功。
  frontend Node14/24、lint/tsc/buildも新規成功。ローカル順序merge #6→#3→#4も競合なし（最終beac374）。
  フロントと順序・Hosting案は同意済み。#4は現在base=frontendで、#3統合後のmainへの変更/再確認が必要。
- 詳細：[夜間ステータス](backend-a-night-status.md)、[配備/rollback準備](backend-a-deployment-runbook.md)。
  Docker daemon socketなしでbuild/run未検証。実機/実UI/実OIDC/Tasks/Run/料金は未検証。
- 次回は本ブランチのgit status/logと最新remote/PRコメントを確認。新headだけ再検証し、待ちだけなら停止してよい。
  G2/G3への自動移行・利用枠回復後の自動再開なし。

## 最新：フロント修正後のG1再検証（2026-11-08）

- フロントAIとPR #3で分担合意。frontend/はフロントが所有し、Aは外部harness/Emulator/HTTPを担当。
- main `c8e2375`、frontend `3db187b`、frontend-effects `dd6794b` を取得。
  検証用ローカルmerge `3d9aefa` / `3111b29`。main/frontendへPushせず、元Aの未追跡文書も保全。
- Aの共有用ブランチは **codex/g1-validation-handoff**。main起点でfrontend/の差分なし。
  tools/validate_frontend.mjsとrun_g1_emulator_checks.shを分離し、別checkoutの現行factoryを検証する。
- mainのB変更を保持。古いB出所digestの1失敗を修正（manifestをc8e2375へ更新、全13ファイルdigest/Job schema検査を維持）。
  Bソース/共有型/API/ゲームルールには変更なし。
- **新規結果**：offline139 passed/3 skipped、Emulator142 passed（22.55秒）、Rules5 passed、
  PR #3 frontend14 passed、PR #4 frontend24 passed、各lint/tsc/通常・Emulator build成功。
  両PRのfactory・現行startHeartbeat・3匿名UID・14 API・4購読・PNG/MP4・401再送・B実Worker+MockAIで一巡成功。
  各8ケースの購読エラー注入成功。PR #4のcountdown=10秒はローカルfixtureだけ。
- 残る静的指摘はmain由来worker3件とB test_odaiのformat1件。A/共通側のcheckは成功。
- 最新mainによりchangelog競合が再発。検証用では両記録保持で解消したが、元PRの取り込みはフロント担当。
  mainへマージ可能とは断定しない。ブラウザ/React effect/実録画/実機/HTTPS/実Cloud/実AIはAで未検証。
- 詳細と再開手順：[g1-revalidation.md](g1-revalidation.md)。G2は[g2-readonly-survey-plan.md](g2-readonly-survey-plan.md)の未実行計画のみ。
- 次回最初：本ブランチのgit status/log -1、最新main/frontend/effectsとPR #3の返答を取得。
  フロントの再統合済みheadが届いたらsource差分を確認して再検証。今回の結果を別headの成功として使わない。
- PR #3/#4のmainマージ、実Cloud読取/設定変更/デプロイ、Auth有効化/ドメイン追加、実configの10秒設定は人間の別途承認待ち。
  自動再開・G2実調査・G3への自動移行なし。最後のコミットは本節を含むgit log -1で確認する。

## 最新：PR #2の最終マージ承認・直前再統合（2026-11-08）

- ユーザーが「現在はデプロイされていないことを確認したため、最終マージを承認」と明示。コードマージだけ承認され、実Cloud/再デプロイ/課金/G1マージは不許可のまま。
- Ready化直後の再確認でmainが6c45990→a0cc2efへ更新され競合を検出。実マージは行わずDraftへ戻してAに取り込み直した。
- Bの切替先429で待たない改善、別モデル/ロケーションfallback、共有型の実装追随文書と承認待ち表、実験スクリプトを保持。
  実験スクリプトは実行していない。唯一の競合は生成済み.pycのmodify/deleteで、追跡解除を維持しBソースを変更しない。
- Aのfake SDK cacheのキーを新しいB実装へ適合。出所manifestをa0cc2efへ更新。既存未追跡ab-agent-coordination.mdはそのまま保全。
- **オフライン136 passed/3 skipped、Emulator139 passed（24.59秒）/Rules5 passed、匿名3人の実HTTPゲーム成功**。
- 最終main/head/保護/レビュー/チェックを再確認し、テスト済みAを通常Push後、Ready化・通常マージする。auto-mergeは使わない。
- Webhooks/Appsの設定自体はAで未確認。未確認を確認済みにせず、今回のユーザー明示承認の範囲でのみ実行する。
- G1の補完案286de53は別ブランチ。G0のmain統合を受けた再base/検証はG1側で別途進め、G1のmainマージは今回行わない。

## 前回：G0正式着手・G1並行（2026-11-08）

- ユーザーがG0/G1の並行開発と、条件をすべて満たした場合だけのmainマージを許可。実Cloud接続/変更/デプロイ/課金は今回一切不許可。
- origin/main **6c45990**をcodex/backend-aへ取り込み。内容競合なし。Bの429再試行・provider切替・座標前処理・プロンプトを保持。
- Bの明示同意6716769715/6716835926を読み、docs/ab-coordination.mdのA返答と運用上の未確定事項を記録。
- Bのソースはmainとバイト一致。生成済み.pyc10個だけ追跡解除（ディスク上は保持）。Bの追加テスト2本はformatのみ。
- 新規G0接続テスト：Aのsequence数値順・重複先着維持→Bの前処理→結果保存、SDK内429→provider切替→Aの1回確定→二重配送を確認。
- **オフライン130 passed/3 skipped、Emulator133 passed（25.02秒）/Rules5 passed、匿名3UIDの実HTTP一巡成功**。
  G0専用ポートを使いG1の開発Emulatorと分離。実SDK通信はfake、実モデル/ADC/キーは使わない。
- ruff44ファイル、compileall、uv lock/check、66パッケージ整合、TS型25例、diff検査成功。
- GitHub mainはprotected=false、rulesetsなし、PRのformal reviewは0件（B同意コメントあり）。保護詳細APIは403。
- **最終マージのみ停止**：Webhooks/Installed Appsが未確認。コネクター未対応、Firefox Computer Useも利用許可なしで確認不能。
  不明な外部デプロイ経路を安全と推測せず、Draft維持、Ready化/mainマージ/auto-mergeをしない。G0の統合/テスト/通常Pushは継続。
- G1は別worktree .tools/g1-worktree・codex/frontend-real-backendで実装を並行開始。G0へ変更を混ぜず、G1のmainマージは禁止。
- 既存未追跡docs/ab-agent-coordination.mdは保全しコミットに含めない。
- 詳細は **docs/g0-status.md**。次は管理者のWebhooks/Apps/外部CI確認記録、G1のローカル結合結果。
  Cloud/SA/IAM/課金/Scheduler/実AI/デプロイは別途承認が必要で、G2へ自動移行しない。

## 前回：PR #2へ最新mainを取り込み（2026-11-08）

- 開始時codex/backend-a=origin/codex/backend-a=88fc796、cleanを確認。fetchでmainのaa9d9c5→82bf14eを検出。
  新規3コミットは画像24時間保存、形式確認スクリプト、PNG実測報告。mainはローカル2184eadから変更していない。
- Aブランチに最新mainを取り込み。競合はdocs/changelog.mdの1件のみ。
  Aの承認済みmy-input秒数API追加とBの画像24時間決定を両方残して解消。仕様書の両変更も維持。
- Bの生成画像は24時間のStorage lifecycleへ決定。leave/startは録画のみ削除のまま、画像の個別削除は追加しない。
  Storage実体消失後は既存assets APIが404/ASSET_NOT_FOUND、履歴・結果metadataは維持。
  新規2テストで画像消失後の履歴/認可/ゲーム状態とGoogle Storage NotFound→404変換を確認。
- PNGの確認はBの報告（image/png/PNG signature/約1.2MB）を正本から反映。
  scripts/check_image_format.pyは取り込んだが実行していない。実バケット全体の24時間設定もB報告であり、Aは実環境未接続。
- ユーザーからA/B結合のB了承を受領。B画像のTasks/OIDC提案はteam-integration-guide.mdへ整理。
  queue名は例、SAとdeadlineの実URLは未確定。環境変数の適用・SA/キュー作成・実URLアクセスはしていない。
  Workerと期限サービスのINTERNAL_AUDIENCEはそれぞれ自身のベースURLとする。
- **検証成功**：オフライン118 passed/3 skipped、Emulator **121 passed / Rules 5 passed**（26.40秒）。
  実B Worker結合、Transaction/冪等性/進行復旧、匿名3UIDの実HTTP一巡も成功。Emulatorのlifecycle削除は模擬。
- ruff41ファイル、compileall、uv lock/check、66パッケージ整合性、フロント型25例、diff検査成功。
  Bのworker/dataとmainフロントは最新mainと一致。JobPayload/JobResultとwrite_job_result→advance_stepを維持。
- Dockerはdaemon socketなしでbuild/run未検証。実AI/実キュー/IAM/Cloud Run/実機ブラウザも未検証。
- 本記録を含むマージコミットをAへ保存し、成功したテスト結果を確認してから通常Push。PR #2のmergeableを再確認する。
  mainへのマージ・自動マージ・デプロイ・実環境操作は禁止のまま。Draftは維持。
- 次はSA/キュー/deadline URL等の運用値の決定、実フロント・実機・Docker検証。実Cloudは別途明示承認が必要。

## 前回：Pushとmain起点のマージ検証（2026-11-08）

- ユーザーの明示許可で `origin/codex/backend-a` へ**通常Push成功**：afd375f→64eb82e。
  PR作成/mainへのPush/mainへのマージ/強制Push/実Cloud操作は行っていない。
- Push前はclean。126追跡ファイルと未Push履歴148blobsを秘密情報・不要ファイルのパターンで検査し検出なし。
  gitleaksは未導入。未知の秘密まで完全に検出したとは主張しない。
- Push後に最新origin/main aa9d9c5を取得。main起点の一時ローカルブランチ
  `codex/backend-a-merge-check-64eb82e` で実際にAを試験マージ。**競合0件**、コードはPush済みAと一致。
  一時結果は `c983f49` で保存しPushしない。ローカルmainは2184eadのまま。
- マージ後の検証：オフライン116 passed/3 skipped、Emulator **119 passed / Rules 5 passed**（23.64秒）。
  B実handler/jobsとA進行、Transaction/冪等性/保存後の復旧を検証。
- 匿名認証3人の実HTTPゲーム完走、フロント型25例、依存lock/66パッケージ整合性、
  wheelの別install/起動、ruff41ファイル、compileall、shell構文、diff検査も成功。
- Dockerはdaemon socketなしで実行不能。実クラウド・実AI・実キュー・実機ブラウザは未検証。
- worker/main.pyはmain版のLogSinkのまま。永続化はapi.worker:app + GameJobIO/Sinkで確認した。
  入口の採用/保守分担、画像保持/TTL、キュー担当/SA、PNG/入力上限はBへの確認待ち。
- 詳細は **backend-a-merge-validation.md**。必要なコード修正・新しい共有契約変更はなかった。
  検証記録をAブランチへ保存して通常Pushする。現在はcodex/backend-aへ復帰済み。
- 次は担当者レビューとDocker/実フロント結合。実Cloudやmain操作は改めて許可が必要。監視/自動再開なし。

## 前回：チーム結合準備と録画秒数API（2026-11-08）

- 作業ブランチ `codex/backend-a`。開始時HEAD `edf835a`、未コミット変更なしを確認して継続。
- read-only fetchしたorigin/mainは `aa9d9c5` のまま。既にHEADの祖先なので追加マージ不要。
  リモートAへのreset/pullは行わず、ローカルmain `2184ead` は変更していない。
- **実装済み**：人Bのmy-inputにcountdown_seconds/record_secondsを追加。ラウンド開始時config snapshotから返す。
  カウントダウン0秒/7秒、config変更後も値を維持、再取得・gesture/start後も値/締切が同じ、
  A/C/非参加者の拒否、A/Cの応答に項目を追加しないことを実B Worker結合テストで確認。
  ユーザー承認に基づきspecification/changelogへ記録。他の秒数や猶予/離脱ルールは変更なし。
- API機能コミット：`7061ad4`。開発用入口・チーム資料はこの記録を含むHEADに保存（git log -1で確認）。
- **実装済み**：api.localの開発用入口。A公開API+B実handler/jobs+MockAIClient+A永続IO/Sinkとメモリ配送を1プロセスで実行。
  local/emulator以外をSDK生成前に拒否。既存APIの初期化/保守lifespanも保持。実Cloud/本番Workerの代用ではない。
- **検証済み**：オフライン **116 passed / 3 skipped**。隔離uv.lock環境のEmulator Suite **119 passed / Rules 5 passed**（21.54秒）。
  新規のローカル配送による3人一巡、録画未保存時のC待機、期限前の非実行、lifespanによる自動配送、Cloud拒否を含む。
- **HTTP結合検証済み**：tools/smoke_local_team.pyで一時uvicornをloopback起動し、Auth Emulatorの異なる匿名UID3人で
  create/join/role/start→初期画像取得→文章→人Bの秒数取得→finish→動画保存→C提出→最終履歴→帰還を実行。
  B実WorkerとFirestore/Storage Emulatorを通し、API/Emulatorの終了まで確認。実ブラウザ・実カメラの検証とは区別する。
- 実応答/公開文書25例を再生成し、mainのフロントTS型へ代入する検査も成功。フロント内部は変更なし。
- 重点7ファイルの比較は **shared-file-review.md**。worker/main.pyを含むworker/dataはmainとバイト一致。
  JobPayload/JobResult等のスキーマ一致、write_job_result→advance_stepの契約を維持。
  座標上限・設定の配布・画像保持・起動入口/保守分担の差異はB/フロントへレビュー依頼として記録。
- **担当者へ渡す資料**：team-integration-guide.md（URL・認証・CORS・購読先・API入出力・IO/Sink・ジョブ・起動/テスト手順）。
  integration-handoff.mdも更新し、承認済み秒数追加を未解決扱いから外した。
- **未検証**：Docker CLIは存在するがローカルdaemon socketなし。docker infoで接続不能を確認しbuild/runは未実行。
  実フロントBackend、実機録画、Google Cloud/Firebase実環境、実AI、Cloud Tasks実配送、IAM/デプロイは未検証。
- **未承認**：Push/PR/mainマージ、実環境操作、画像保持方針、猶予10秒/離脱30秒/設定秒数の確定。
  許可待ちの操作は実行していない。Bやフロントへメッセージ送信もしていない。
- 次の作業：team-integration-guide.mdを担当者に渡し、実Backendの接続/共有差分をレビュー。
  Dockerが使える環境でbuild/run、その後ユーザーの明示承認範囲でGitHub共有・実環境検証を行う。自動再開/監視なし。
- 公式利用状況：5時間枠11%使用（89%残）、週枠76%使用。課金変更・クレジット購入・リセットなし。

## 前回の状態（2026-11-08・main更新のローカル統合）

- 30分ごとのGitHub監視 `a-github` はユーザー指示で解除済み。自動再開しない。
- `origin/main aa9d9c5` を `codex/backend-a` 側で統合。API/Worker/共通設定/依存/Docker等の11ファイルの競合を整理。
  ローカルmainは `2184ead` のまま。Push・PR・mainへのマージなし。
- 変更のあるmainのWorker/dataとフロントを取得。worker/dataはmainとバイト一致し、フロント内部・AI内部は変更していない。
- **担当者へ転送する確認事項：integration-handoff.md**。未合意の録画秒数API追加・猶予/離脱秒数変更は適用していない。
- 共通設定はBのget_settings/処理別provider/GCP_PROJECT/STORAGE_BUCKETと互換化。明示Cloud opt-in・ローカルmock制限を維持。
- 共通StorageはBの注入口を維持し、録画のみ削除・失敗記録保持・Timestamp保存へ統一。
- 同じDockerイメージで `SERVICE_ROLE=api|worker|deadlines` を選択。永続Worker入口はapi.worker:app。
  デプロイスクリプトはworker role/必要設定を要求し、未設定ならgcloud呼出前に停止する。
  テストでは偽のgcloud実行ファイルで引数だけを確認し、実コマンド/認証情報は使用していない。
- Emulator runtimeは明示したloopbackのStorage Emulatorを共有できる。外部host/不一致hostは拒否。
- 初回Emulator実行で同時提出のABORTED再試行枯渇を再現。SDK即時5回×外側3回から、
  1回ごとに新snapshotを取り指数的full jitterを置く合計8回の限定再試行へ修正。
  業務エラーは再試行せず、同時提出テストの件数/成功条件は緩めていない。
- **ローカル検証済み**：uv.lockから隔離環境を構築、オフラインPython **110 passed / 3 skipped**。
  Emulator Suite **Python 113 passed / Rules 5 passed**（29.40秒）。
  Auth匿名トークン、Firestore競合、別Worker SDKクライアント、Storageの保存/再生/削除、実B handler/jobsを含む。
- uv.lockの隔離環境でもEmulatorを再実行し、**Python 113 passed / Rules 5 passed**（25.71秒）。
  読取中の競合に加え、再試行上限8回/業務エラー非再試行を単体テストで検証。ログは.tools配下（Git対象外）。
- A/Bの実応答・公開文書25例を生成し、mainフロントのTS型への代入検査成功。フロント自体のtsc -bも成功。
  mainのフロントはmock固定であり、実HTTP/Auth/Firestore Backend接続はフロント担当の未実装作業。
- **未検証**：Docker daemonなしでbuild/run不可。フロントbuild/lintは同梱Nodeのネイティブ拡張Team ID不一致で停止。
  依存lockや署名保護は変更していない。通常のNode環境で再実行する。
- **実環境未検証**：Google Cloud/Firebase/実AI/キュー再配送/IAM/Run/Hosting/Rules適用/実機録画。
  今回これらへの接続・認証情報使用・外部書込みは実行していない。
- 依存ロックは統合pyprojectからuv.lockを再生成し、同じ内容からrequirements.lockを書出し。
  wheel build/隔離install/ソース外からのWorker起動、ruff、compileall、pip/uv pip check、shell構文も成功。
- 再開時は `git status --short` / `git log -5 --oneline` とこの文書、integration-handoff.mdを確認。
  次は担当者の未合意項目への回答を反映し、通常Node/Docker環境で検証。実環境やPush/PRは別途承認待ち。
- 現ブランチは `codex/backend-a`、本統合直前のコミットは `7b997bd`。本記録を含む保存先はHEAD（git log -1で確認）。

以下は前回フェーズの履歴。現在の状態・確認依頼は上記とintegration-handoff.mdを優先する。

## 実行制限・合意

- 日本時間22:00〜翌07:00はユーザー不在。自動再開しない。
- 実クラウド接続・Google認証情報使用・外部書き込み・Push・PR・マージは行わない。
- 2026-11-07の会話で§11案、履歴の表優先、離脱者未帰還時は新しい部屋、共有ファイルのA実装が承認済み。
- Worker本体・再試行・AI・お題・Cloud Tasks基盤・StorageライフサイクルはB担当。
- ローカル `main` は変更していない。最新origin/mainのB実装をread-only fetchし、worker/dataだけをそのまま取り込んだ。
- 前回のGitHub読取監視は、2026-11-08にユーザー指示で解除済み。

## 仕様・Bとの境界

最新origin/mainのshared-types §11 #3はA合意済み。今回その記録だけを取り込んだ。
`write_job_result`→`advance_step`の方針は確定し、apply_job_resultは復活させない。
Bのhandler/jobsは実装済みだが、worker.mainのLogSinkはログのみで永続結果保存は未実装だった。
AのGameJobIO/GameJobSinkでBの既存Protocolを実装し、Bのhandler/jobs/AIモックを変更せず通す。
worker/・data/の12ファイルはf72e714とバイト一致。docs/backend-b-source.jsonとテストで照合。
Bのworker.mainはget_settingsが必要でA設定と未統合。認証済みの注入式create_worker_appを別途用意。
Bの共通Storage実装は画像も削除するため採用せず、承認済みの録画のみ削除を維持。
共有モデルの引数・JobPayload/JobResultスキーマは変更していない。

## 実装済み

- 共通列挙型・ジョブ/アセット/座標モデル・設定（仮の秒数は差し替え可能）
- 明示的なCloud opt-in、local専用認証、Firebase検証アダプター
- ロールバック付きメモリ保存と、読取後に書込むFirestore Transactionアダプター
- StorageとAssetDoc保存、録画のみの削除、永続outboxとCloud Tasks配送アダプター
- MIME・先頭バイト・コンテナ・時間・解像度を検査する録画検証
- FastAPI 14 API、入力検証・日本語の共通エラー、body上限、限定CORS、no-store
- 部屋・参加コード・総当たり制限・役割排他・ホスト開始・サーバー時刻・同意記録
- request_id再送は同じ応答、内容変更は拒否。同時提出・同時再送をTransactionで確定
- my-input、各人の段以前だけの履歴、終了/失敗後の全履歴、帰還後の閲覧拒否
- 座標バッチ（欠番許容・連番重複無視・有限値/21点/仮250KB上限）
- 録画保存とfinishの両条件でCへ進行。Storage/metadata失敗時は進行しない
- 締切+猶予、未提出と離脱の区別、全プレイヤーの監視、古い期限/監視再配送の無害化
- 進行のadvance_stepをAPIとBのWorkerで共有できる初期化口
- 削除失敗の永続再試行。全員帰還/次回開始で録画だけ削除し、画像を保持
- Firestore/Storage Rules、Emulator Suite、固定依存、DockerfileとRun/Hostingの設定案
- 第2フェーズ：B実handle_job/run_jobに接続するIO/Sink、Bのお題選択・PNG保存・結論・類似度を永続化
- 結果とadvance_pending/progress_outboxを同一Transactionで確定。進行失敗はAI再実行なしで復旧
- AIの最終試行後にキュー再配送がなくても、Aの保守処理/heartbeatが進行outboxを再実行
- 推論前のexecution_outboxでプロセス停止を検出。残り試行があれば別名タスクを再登録し、3回消費済みなら失敗確定
- 内部WorkerアプリはBの/tasks/runと既存/internal/jobsを認証付きで受け付け、公開APIには登録しない
- OpenAPIの自動422表記を実際のS1の400形式へ修正。14 APIのパス・メソッド・成功HTTPを仕様書と照合
- 可視STEPに属していても、outputsに採用されていないアセットは取得不可に修正
- Firestoreの同じTransaction内の読取をキャッシュし、SDKが再試行しきれないABORTEDだけを新Transaction+短いjitterで再試行

## 検証

- 第2フェーズ：オフライン **90 passed, 3 skipped**（2.14秒）。B実Worker結合・クラッシュ復旧・競合・スキーマ/ソース一致を含む。
  skipはEmulator専用のAuth、Storage、別API/Workerクライアント構成。
- 第2フェーズ：Emulator Suite **Python 93 passed（56.94秒）/ Rules 5 passed**。実推論だけをBのMockAIClientに置き換え、B実handler/jobsを通した。
- 第2フェーズ：別々のAPI/Worker用Firestore・Storage SDKクライアントで3人ゲームを検証。
- 第2フェーズ：wheelをローカルbuild/別ディレクトリinstallし、B Worker・odaiデータ・注入式アプリをソース外からimport確認。
- 第2フェーズ：直前の再実行で12同時提出のTransaction lock timeoutを再現。テストを緩めず、読取キャッシュとABORTEDだけの限定再試行を修正。
  修正後は12同時提出×5回を含めて成功。任意のValueErrorや業務エラーは再試行しないことも検証。
- 第2フェーズ：ruff check/format --check（31ファイル）、compileall（Bも含む）、pip check、git diff --check、shell構文検査成功。
- 第2フェーズ：23:14の公式利用状況は5時間枠16%使用・84%残、週枠64%使用。利用量による停止ではない。
- GitHub読取確認でmainのd821bea（B確認文書）を検出。Worker変更なし、リモート作業ブランチはafd375fのまま。
- Docker daemonは依然として利用不可。docker APIのソケットなし。実Cloud接続で代替していない。
- 以下は第1フェーズ時点の記録（現在の結果とは区別する）。

- オフライン：`.venv/bin/pytest -q` → **48 passed, 2 skipped**（1.20秒）。
  skipはAuth/StorageのEmulator専用2件。ネットワーク接続を禁止。
- Emulator Suite：**Rules 5 passed / Python 50 passed**（Python 20.22秒）。
  Firestoreは公式SDKの実Transactionで同じAPI/並行送信/障害系を実行。
  Authは匿名トークン・別プロジェクト拒否をSDK経由で検証。
  失効/無効ユーザーの拒否とcheck_revoked指定はSDKモックで検証。
  Storageは公式SDKによるMP4保存・取得・削除を専用テストで検証。
  WebM/MIME/拡張子、生成画像保持も検証済み。
- ruff check、ruff format --check（26ファイル）、compileall、pip check、bash -n、git diff --check成功。
- エミュレーターはdemo-gesture-relay、127.0.0.1のみ。匿名/ダミー認証を使用し実Google認証情報なし。
  エミュレーター停止まで確認。Google Cloud・Firebaseの実環境は未接続。
- 非致命的な警告：Starletteのhttpx非推奨1件、Java25でStorage EmulatorのUnsafe警告。
  RulesテストのPERMISSION_DENIEDログは拒否を確認した期待結果。
- 最終公式使用状況（22:17 JST）：5時間枠24%使用・**76%残**、週枠60%使用。
  課金変更・クレジット購入・使用枠リセットは実行していない。利用枠停止ではない。
- Python 3.11は /opt/homebrew/bin/python3.11。仮想環境 .venv に依存導入済み。

## 未実装・未検証とブロッカー

1. Bの実handler/jobs/MockAI/FileOdaiSourceとのローカル結合済み。実モデルと本番Worker設定は未検証。
2. 正本のwrite_job_result→advance_stepはmainで合意済み。GameJobIO/Sinkの本番配置と設定統合をBに確認。
3. Bのworker.mainはget_settings/LogSink/MemoryJobIOに依存し、そのままではA Settingsと未統合。create_worker_appで回避したが、本番入口の一本化はBと要確認。
4. 実Firebase IDトークン、実Firestore/Storage/Cloud Tasks再配送、IAM、Cloud Run、Hosting。
   不在時の禁止事項のため実行しない。SDK呼出形はモックとエミュレーターで検証済み。
5. Dockerイメージbuild/run：Docker daemonのソケットが存在せず実行不能。
   Dockerfileは用意済み、daemonを起動できる環境で確認する。
6. 秒数・生成画像保持期間・類似度表示など未決定のゲーム仕様は確定していない。
7. 実際のiPhone/Androidでの録画・再生互換はフロントとの実機確認待ち。
8. 第1フェーズのafd375fまではユーザー承認でPush済み。第2フェーズは新しい禁止指示に従いローカルのみ。PR未作成。
9. 生成画像削除・Timestamp保存・Cloud Tasksキュー作成担当にB文書との相違。backend-a-confirmation-response.md参照。
10. outbox回復はAの保守処理/heartbeatの実行が前提。無稼働のCloud Runでの回復時間・IAM・キュー設定は未検証。

## 再開時の手順

1. ユーザーの手動再開指示を受けてから、この文書と `git log -5 --oneline`、`git status --short` を確認。
2. `codex/backend-a` を使う。新たな変更があれば上書きしない。
3. `.venv/bin/pytest -q`、ruff check/format --checkで状態確認。
4. docs/backend-a-confirmation-response.mdを参照し、Bの本番入口・設定・Storage・担当の差異を整理する。
5. エミュレーター再実行方法はREADME。Docker daemon起動後にローカルbuild/run。
6. ユーザーが改めて許可したらPushとDraft PR。クラウド接続はそれとは別に承認を得る。
7. mainへのマージはユーザー在席かつ明示承認時だけ。自動マージはしない。

## ブランチ・コミット

- 作業ブランチ：codex/backend-a
- 第2フェーズのB取込コミット：`1f84f9f`（worker/dataはf72e714とバイト不変）。
- 第2フェーズの実装コミット：`8a94dc1`（永続IO/Sink・復旧・競合修正・93テスト）。最新HEADは文書仕上げを含む。
- 第1フェーズ最後の実装コミット：`eb8f641`（50件のEmulatorテスト成功後の実装・テスト保存）。
- 前の機能コミット：`6a92b47` 共通基盤、`8abbb30` API/3人進行。
- 最新コミットは `HEAD`（この進捗とインフラ/レビュー資料の仕上げ）。`git log -1 --oneline`で正確なhashを確認。
- Gitメタデータの書き込みにサンドボックス外の承認が必要。

## 主な作成・変更ファイル

- api/app.py・models.py・main.py・internal.py：14 APIと公開/内部アプリ。
- backend_a/game.py・progress.py：Transaction、進行・公開範囲・共有口。
- backend_a/auth.py・store.py・runtime.py・tasks.py・video.py：SDK/ローカル切替、配送、録画検証。
- common/enums.py・models.py・settings.py・storage.py：共有型・設定・アセット。
- tests/：3人ゲーム・異常系・SDK・Auth/Storage Emulator、50テスト。
- firestore.rules・storage.rules・firebase.json・.firebaserc・tools/emulator/：ローカルRules検証。
- Dockerfile・infra/・pyproject.toml・requirements.lock・.env.example：設定/導入案。
- README.md・backend-a-integration.md・backend-a-pr.md：セットアップ、Bへの確認事項、PR本文案。
- 正本のspecification/shared-types/changelogは取得版のまま。会話の承認はこの文書とintegrationに記録。
- 第2フェーズ：backend_a/worker_bridge.py・api/worker_app.py・tests/test_worker_integration.py/worker_contracts.py/s1_contract.pyを追加。
- docs/confirmation-items.mdはd821beaのB文書を無変更で取得。Aの回答は別ファイルbackend-a-confirmation-response.md。

## 承認・外部検証待ち

- 実Firebase Auth/Firestore/Storage/Cloud Tasks/Cloud Run、IAM、コスト、デプロイ。
- Push・PR作成はユーザー在席時の新たな許可待ち。mainマージは明示承認時のみ。


## PR #8 最終検証（#6統合後のmain150df95基準）

- 専用branch codex/firestore-local-admission。製品修正はStore内RLockの8行を維持。
  例外/ABORTED/SystemExit後の別thread解放4ケースとStore独立性1ケース、ローカル性能計測ツールを追加。
- 新規：単体offline144/skip3・Emulator147/Rules5・14 API/B MockAI/3人完走。
  #7 head1329740との隔離併用はoffline163/skip3・Emulator166/Rules5・3人完走。
  pytest期待値を緩めず、12提出5回の既存テストも保持。
- 12提出×3組のbefore/afterは両方3/3正解（成功率差は未観測）。平均HTTP応答1,887.1→24.9ms、
  after lock待ち平均13.0ms/最大27.4ms。一方、非DBの独立20ms callback対照は約8.2倍遅くなる。
  G1単一Store/3人用途では統合推奨、多部屋/多instance/実Cloud性能は未保証。
- 初回の設定テスト2失敗はrunner env固定が原因。後続suiteのfixture HTTP499は
  clearDataとキャンセル済みWatch通知のEmulator競合。新規専有Suiteへ隔離し再成功。skip/xfail化なし。
- A変更のruff/format/diff成功。既存B lint3/test_odai format1は未解消・変更なし。
- 詳細と再現手順はdocs/firestore-contention-audit.md。生ログ/JSONは.toolsのみ。
  PR #8のReady化/判定/最新フルSHAはGitHub監査コメントが正本。
- 次回：最新main/各PRを取得し対象SHAの一致を確認。#8は個別承認待ち、main mergeは未実行。
  #3追従はフロント担当に依頼し、#4/#7のmerge/base変更・G2実読取・IAM/配備/実AI/課金へ自動移行しない。

### 最新main7e4b4ebへの追従

- mainの3追加commit（お題44件、B録画時刻/実験記録）を保持して取り込み。実AIスクリプトは未実行。
- odai hash不一致を既存testが検出したため、B由来13ファイルをmainとバイト照合し、由来manifestだけ更新。
- 最新基準で新規再実行：#8 e36d65c offline144/skip3・Emulator147（9.78秒）/Rules5/3人PASS。
  #7併用d2208ee offline163/skip3・Emulator166（12.26秒）/Rules5/3人PASS。各14 APIとB実Worker+MockAIを通す。
- 以後は監査文書のみ追記。性能測定は初回main150df95基準の数値として区別する。
- #7 B再レビュー6723006930は150秒子process設計に同意。実ADC・cold start込み180秒余裕・複数instance重複は実環境未検証。
  実DEADLINE_URL/実行SA emailは未確定。#7のbase変更/mergeは未実行。

### PR #8 承認直前のまとめ確認

- main6f1efa4の追加はB実験文書17行だけ。取り込み済みで検証済みコード/テスト/Rulesと一致。
- ロック安全性5件を追加実行し成功（0.18秒）。全Emulator再実行とは報告しない。
- #8のみ人間の個別merge承認待ち。承認後は#3/#4の監査をまとめ、所有branchへのPushやCloud操作へ拡張しない。
