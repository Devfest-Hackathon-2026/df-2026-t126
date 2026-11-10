# 今日のチーム結合手順（Aからの引継ぎ）

2026-11-08。対象はローカル `codex/backend-a`、main基準 `aa9d9c5`。
ユーザー許可でGitHubのAブランチを `afd375f` から `64eb82e` まで更新済み。
作業前にローカルとの差を確認し、reset/pullで上書きしないこと。最新の検証記録はbackend-a-merge-validation.md。
この文書のURLはローカル検証用であり、実環境のURLではない。
実Cloud接続・本番認証情報・デプロイ・PR/mainマージは実行していない。Aブランチだけ許可に基づき通常Push済み。

## 1. フロント担当へ渡す接続情報

| 項目 | ローカル検証用の値・条件 |
|---|---|
| API origin | `http://127.0.0.1:8000`。パスは `/api/...` を含める |
| フロント origin | `http://localhost:5173` をCORSに許可。127.0.0.1で開くならそのoriginも明示追加 |
| Firebase project | `demo-gesture-relay`（実プロジェクトを使わない） |
| Auth Emulator | `http://127.0.0.1:9099`。匿名ログインのIDトークンを使う |
| Firestore Emulator | `127.0.0.1:8080`。Firebase Web SDKを明示的にEmulatorへ接続 |
| Storage Emulator | `127.0.0.1:9199`。ブラウザから直接使わずassets API経由 |
| HTTP認証 | 全14 APIに `Authorization: Bearer <匿名IDトークン>`。期限切れ時はトークン更新 |
| 入力形式 | JSONはContent-Type application/json。request_idはUUID。再送は同じID・同じ内容 |
| 時刻 | APIはUTCのISO 8601、FirestoreはTimestamp。Web側でtoDate().toISOString()などに揃える |

### 起動方法

Python依存はREADMEどおり導入し、Emulator依存は `tools/emulator` の固定lockを使う。
まず端末1でEmulatorだけを起動する（CLIログイン・本番認証情報は不要）。

```bash
env -u GOOGLE_APPLICATION_CREDENTIALS -u FIREBASE_TOKEN \
  CI=true XDG_CONFIG_HOME="$PWD/.tools/config" \
  FIREBASE_EMULATORS_PATH="$PWD/.tools/emulators" \
  tools/emulator/node_modules/.bin/firebase emulators:start \
  --project demo-gesture-relay --only auth,firestore,storage
```

端末2でAPIとモックAIの開発用配送を起動する。

```bash
env -u GOOGLE_APPLICATION_CREDENTIALS -u FIREBASE_TOKEN \
  RUNTIME_MODE=emulator ENABLE_CLOUD=false AI_MODE=mock \
  PROJECT_ID=demo-gesture-relay BUCKET_NAME=demo-gesture-relay.appspot.com \
  FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 \
  FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099 \
  FIREBASE_STORAGE_EMULATOR_HOST=127.0.0.1:9199 \
  CORS_ORIGINS='["http://localhost:5173","http://127.0.0.1:5173"]' \
  .venv/bin/uvicorn api.local:build_local_app --factory --host 127.0.0.1 --port 8000
```

`api.local` はAのAPI、Bの実handler/jobs、MockAIClient、Aの永続IO/Sinkを組み合わせる。
Cloud Tasksの代わりにメモリキューを配送し、期限もサーバー時計で処理する。Cloud Tasksの実再配送の証明ではない。
**1プロセスで起動**する。再起動時はメモリ配送状態が失われる。実運用ではこの入口を使わない。
本来のAPI用入口 `api.main:app` だけではAIジョブが自動実行されないため、手動デモには上の入口を使う。
ハートビートを5秒ごとに送る。保守処理は結果保存後の進行・推論停止・削除のoutboxを回復する。

Web側はダミーのFirebase Web設定（例: apiKey=demo-key、projectId=demo-gesture-relay）でアプリを初期化し、
Auth/Firestoreを上記Emulatorへ**ログイン・購読前に**接続する。実プロジェクトのWeb設定や本番トークンは使わない。
3人は異なる匿名UIDが必要。同じブラウザの通常タブはログイン状態を共有するため、独立したブラウザプロファイル等を使う。
端末上のlocalhostは端末自身を指す。ここではLAN公開していないため、iPhoneからこのURLで接続できたとは扱わない。
実機用の接続経路・HTTPS/カメラ権限はフロントと別途準備する。

認証もDBも使わないAPI単体確認は、同じ開発用入口をRUNTIME_MODE=localで起動し `Bearer local:a` 等を使える。
その場合はFirestore購読もメモリとは連動しないため、フロントのFirebase結合確認には使わない。

### Firestore購読先

| 対象 | パス | Web側の処理 |
|---|---|---|
| 部屋 | `rooms/{room_id}` | current_round_idの変更時に古いround/steps購読を解除して付け直す |
| 参加者 | `rooms/{room_id}/players` | doc.idをUIDにしてRecordを作る |
| ラウンド | `rooms/{room_id}/rounds/{round_id}` | status/current_step_index/gesture_ai_status/result_statusを見る |
| STEP | `rooms/{room_id}/rounds/{round_id}/steps` | step_indexで数値順に並べる |

入室API成功後、同じUIDで購読する。部屋一覧の取得やクライアント書込は禁止。
`config/game`、private、jobs、assets、gesture_batches、result、各outboxは読めない。
中身・履歴・最終結果はHTTP API経由。Storageもブラウザ直アクセスは禁止。

### APIの入出力

メソッド/パス/HTTP statusの正本は specification §3。実応答例25件は
`.venv/bin/python tools/export_frontend_contracts.py` で `.tools/frontend-api-contracts.ts` に再生成できる。
IDの `...` 表記を実リクエストのrequest_idに使わず、crypto.randomUUID等で完全なUUIDを作る。

| 操作 | 主な入力 | 応答・注意 |
|---|---|---|
| create / join | name, consented=true, request_id / joinはjoin_codeも必要 | room_id, player_id / createはjoin_codeも返す |
| role / start | role=A/B/C/null, request_id / startはrequest_id | accepted / startは202でround_idも返す |
| my-input | round_id | step_index,type,deadline_at,input。**gestureのみcountdown_seconds,record_secondsを必ず返す** |
| submit | text,request_id,is_auto | 202 accepted。人Aはstep1、人Cはstep3 |
| gesture/start | request_id | gesture_session_id,deadline_at。締切を延長しない |
| gesture/batches | GestureBatch（連番・mirrored・座標） | 202 accepted。同じsequenceは最初の値を保持 |
| gesture/video | multipart file,gesture_session_id,request_id | 200 accepted,asset_id。Content-Type境界はブラウザに生成させる |
| gesture/finish | gesture_session_id,request_id | 202 accepted。videoとfinishの両方でCが開始する |
| history | round_id | round_status,visible_until_step_index,steps,result。帰還後は403 |
| assets | round_id,asset_id | バイナリ。Bearer付きfetch→Blob URL。Content-Typeを使い、不要時にrevoke |
| leave / heartbeat | leaveはrequest_id、heartbeatは本文不要 | 200 accepted。heartbeatにrequest_idは不要 |

人Bのmy-inputの秒数はゲーム開始時のconfigスナップショット。後から設定が変わっても同ラウンドでは同じ値。
再表示時にカウントダウンを最初から足してdeadlineを延ばさないこと。現在の仮値は60/3/5、猶予5秒、離脱15秒。
猶予10秒・離脱30秒・configの60/10/5は今回承認されていない。
エラーは `{"error":{"code":"NOT_YOUR_TURN","message":"..."}}` 形式。HTTP statusとcodeの両方を扱う。
400は入力不正、401は認証、403は担当/閲覧権限、404は部屋/素材なし、409は状態競合等、429は参加試行制限。

## 2. B担当へ渡すWorker接続情報

- 実Worker処理は `worker.handler.handle_job` → `worker.jobs.run_job`。
- 永続化口は `GameJobIO` / `GameJobSink`（backend_a/worker_bridge.py）。Bの既存Protocolを実装する。
- 結果保存 `write_job_result` → `backend_a.progress.advance_step` の契約を維持。
- 永続Worker用入口は `SERVICE_ROLE=worker` → `api.worker:app`。
  注入してテストする場合は `api.worker_app.create_worker_app(runtime, ai)`。
  元の `worker.main:app` はLogSink/MemoryJobIOのまま保持しているため、永続Workerの起動先にはしない。
- 各プロセスで同じFirestore project/bucketを参照する。別プロセスのMemoryStore/MemoryBlobsは共有できない。
- 公開APIにWorkerルートは登録しない。内部Workerは `/tasks/run`（互換 `/internal/jobs`）でOIDCを要求。
  Emulatorの内部OIDCは拒否する設計。上のローカル開発入口は公開Worker HTTPを増やさず、プロセス内から呼ぶ。

### 保存形式

| 保存先 | 内容 |
|---|---|
| `rooms/{r}/rounds/{g}/private/main` | 開始時players/config/returned_uids、odai_text、outputs（文字列キー）、gesture、gesture_ai_text |
| `.../steps/{index}` | 公開進行状態のみ。秘密の文章/asset_idを入れない |
| `.../jobs/{job_id}` | kind,status,attempt,max_attempts,last_error,revision と内部result/step_index/advance_pending/finalized_at等 |
| `.../gesture_batches/{sequence_number}` | S1のGestureBatch。AIに渡すのは座標のみ、録画は渡さない |
| `.../assets/{asset_id}` | AssetDoc。kind/path/content_type/size_bytes/step_index/created_at（datetime） |
| `.../result/final` | odai,final_image_asset_id,ai_conclusion,similarity,gesture_ai_text |
| トップレベルoutbox | task_outbox、progress_outbox、execution_outbox、cleanup_outbox（サーバー専用） |

`outputs["2"]` の動画参照を裏読み取りテキストで上書きしない。privateのgesture_ai_textを履歴に使い、
最終結果にもコピーする。遅延到着時は両方を更新し、Cのdeadline/revision/メイン進行を変えない。
アセットは実体+AssetDocが保存されてからoutputsへ公開する。未採用アセットは取得不可。

### ジョブ・配送設定

JobPayloadはjob_id/kind/room_id/round_id/step_index/revisionだけ。文章・画像・座標は載せない。
DBのjobからpayloadを作り、round.revisionを後から代入しない。similarityのstep_indexはnull。
同一jobの重複配送・古いrevisionは冪等に扱い、DB上のattemptで推論を合計3回に制限する。
成功/最終失敗は200、再試行中は500。結果保存後の進行失敗でも500になり得るが、再配送ではAIを再実行しない。
結果・advance_pending・progress_outboxを原子的に保存し、advance_stepの成功後に確認を記録する。
最終配送で停止した場合もheartbeat/保守処理がoutboxを回復する。実Cloudのゼロ台時の回復時間は未検証。

本番設定案は PROJECT_ID（互換GCP_PROJECT）、BUCKET_NAME（互換STORAGE_BUCKET）、
TASKS_LOCATION、TASKS_QUEUE、TASKS_SERVICE_ACCOUNT、WORKER_URL、DEADLINE_URL、INTERNAL_AUDIENCE。
OIDC audienceは対象サービスのベースURLで、`/tasks/run` 等を含めない。配送SAのemailもアプリ内で確認する。
本番URL・SAは今回取得していないため未確定。APIと期限サービスの配布値も共同レビューする。
キュー/Worker基盤はB、API enqueueはAという役割表と、B確認文書の想定の差を合意する。

## 3. ローカル検証・Git差分

```bash
.venv/bin/pytest -q
.venv/bin/pytest -q tests/test_worker_integration.py tests/test_local_demo.py
.venv/bin/ruff check api backend_a common tests tools/export_frontend_contracts.py
.venv/bin/python tools/export_frontend_contracts.py
frontend/node_modules/.bin/tsc --noEmit --strict --target es2022 --lib es2022,dom \
  --moduleResolution bundler --module esnext .tools/frontend-api-contracts.ts
```

Emulator Suite再実行はREADME。Dockerはローカルdaemonに接続できず、build/run未検証。
フロント内部はmain版のまま。現mainはmock固定なので、実Backendの実装/切替はフロント担当が行う。
Git上の共有ファイル比較は [shared-file-review](shared-file-review.md)、未合意事項は [integration-handoff](integration-handoff.md)。
Aブランチは通常Pushの許可に基づき共有済み。PR作成・mainへのマージはしない。


実HTTPの3人スモークテストを単独再実行する場合：

```bash
env -u GOOGLE_APPLICATION_CREDENTIALS -u FIREBASE_TOKEN \
  CI=true XDG_CONFIG_HOME="$PWD/.tools/config" \
  FIREBASE_EMULATORS_PATH="$PWD/.tools/emulators" \
  tools/emulator/node_modules/.bin/firebase emulators:exec \
  --project demo-gesture-relay --only auth,firestore,storage \
  'RUN_FIRESTORE_EMULATOR_TESTS=1 .venv/bin/python tools/smoke_local_team.py'
```

スクリプトはデモEmulatorのconfigを60/3/5に設定し、一時APIプロセスと3人分のゲームを作成・終了する。
外部hostのEmulator指定は拒否。ログは.tools/team-http-smoke.log、トークンは出力しない。
これはブラウザ実Backendや実機カメラのテストではない。


## 最新mainの確認とB提供の設定案（2026-11-08）

main 82bf14eを取り込み、生成画像24時間保存とPNG実測報告を反映。画像の個別削除は追加しない。
Storageが実体を削除した場合はassets APIが404/ASSET_NOT_FOUNDを返し、履歴・結果metadataは維持する。
B報告の実バケット設定・PNG確認をA自身の実環境検証済みとは扱わない。scripts/check_image_format.pyは未実行。

以下はユーザー共有のB画像にある**提案/報告値**。実行許可・リソース存在のAによる確認ではなく、環境変数へ自動適用しない。

| 設定 | B提供案・A側の整理 |
|---|---|
| TASKS_LOCATION | asia-northeast1（東京）案 |
| TASKS_QUEUE | gesture-jobsは例。実キュー名/作成担当の確認待ち |
| WORKER_URL | https://worker-122800925175.asia-northeast1.run.app/tasks/run（B提供。Aはアクセスしていない） |
| DEADLINE_URL | Aの既存設計どおり別の非公開期限サービスを使う案。パスは/internal/deadlines、実ベースURLは未取得・未作成 |
| TASKS_SERVICE_ACCOUNT | 専用の配送SAを新規作成する案。名前/メールは未確定、作成・IAM操作は未実施 |
| INTERNAL_AUDIENCE | Worker側はhttps://worker-122800925175.asia-northeast1.run.app。期限サービス側はそのサービス自身のベースURL。パスを含めず、両者に同じWorker audienceを配らない |

A/B結合の了承はユーザーから受領済み。実Cloudへの設定適用、サービス/キュー/SA作成、IAM、デプロイは実行しない。


## G0/G1正式並行後の確定・未確定（2026-11-08）

Bの同意6716769715とmain6c45990に基づく更新。以下はBの確認報告/技術合意であり、Aによる実Cloud照会ではない。

- Worker入口/保守、A Storage正本、TasksのB基盤/A enqueue・期限/outbox、OIDC宛先ベースURL、入力上限/PNGに双方合意。
- queueはB報告でgesture-jobs/asia-northeast1、最大試行3・同時実行4。以前の画像の「queue名は例」やコメントの同時実行10は履歴。
- 専用配送SA tasks-invoker@gesture-relay-game.iam.gserviceaccount.comは案・未作成。API実行SAの実メールとdeadline実URLはAで未作成/未取得。
- Aの方針は専用API実行SA＋別の非公開期限サービス。既存アカウントやURLを推測で実在値として回答しない。
- Bの前処理は最大60サンプル・小数3桁。Aのload_batchesはsequence数値順、同一sequenceは先着値を保持。SDK内再試行/切替はDB job attemptと別単位。
- Aのai_timeout_sは内部再試行を含むジョブ全体の上限。全てのB内部試行の完走を保証しない。設定秒数は変更していない。
- ゼロ台回復はScheduler案を技術案として記録したのみ。Scheduler、最小台数、IAM・費用・実デプロイは人間の別承認が必要。
- G0はEmulator133/Rules5と3人HTTP完走。G1のフロント実装は別ブランチ/worktreeで進め、G0のmainマージを待つ必要はない。
- main最終マージはWebhooks/Installed Apps確認不能で保留。G1のmainマージは今回不許可。G2へ進まない。

G0のテストはFirestore18080/Auth19099/Storage19199の専用loopbackポート。G1は既定ポートか別セットを使い、同じテストDBを消さない。
