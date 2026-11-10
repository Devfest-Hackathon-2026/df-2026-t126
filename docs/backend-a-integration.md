# バックA・B 接続境界（第2フェーズ）

## 仕様の優先・担当

2026-11-08、`origin/main 6c45990` を `codex/backend-a` にローカル統合しました。
Bのworker/data・フロントはmain版のままです。mainブランチ自体は変更していません。
担当者への確認事項は [integration-handoff](integration-handoff.md) に集約しています。
shared-types §11 #3もmainのA合意済み記録に同期。ゲームルール・JobPayload/JobResultは変更していません。
2026-11-08のユーザー承認により、gestureのmy-inputに開始時configの秒数2項目を追加しました。
今日の起動/認証/購読/Worker設定はteam-integration-guide.md、共有差分はshared-file-review.mdを参照してください。
`write_job_result`→`advance_step`を継続し、廃止されたapply_job_resultを復活させていません。

Bの実handle_job/run_job/MockAIClient/FileOdaiSourceを通しています。Bのソースファイルはバイト不変です。
出所はbackend-b-source.jsonに保存し、JobPayload/JobResult/ErrorInfo/JobDocのスキーマも照合します。
BのLogSinkは永続化しないため、Aの接続部がBの既存JobIO/JobSink Protocolを実装します。
第1フェーズのtests/conftest.py.completeとは別に、実Worker用tests/test_worker_integration.pyを追加しました。
実AI・本番Worker設定・IAM・実キューの検証は行っていません。

## 提供する共通口

- `common.enums`、`common.models`、`common.settings`：正本の型と設定。
- `common.storage.save_asset(...) -> str`：Storage成功後にAssetDocを記録。
- `common.storage.delete_round_assets(...) -> int`：録画だけをleave/startで削除。画像は作成から24時間のStorage lifecycleに任せ、個別削除しない。
- `backend_a.progress.advance_step(room_id, round_id) -> None`：進行を冪等に確定。
- `backend_a.progress.can_read_asset(uid, round_id, asset_id) -> bool`：HTTPと同じ認可。
- `configure_storage` / `configure_progress`：プロセス起動時に依存を渡す内部初期化。
- `backend_a.worker_bridge.GameJobIO/GameJobSink`：Bの既存Protocolを実装する永続読み書き。
- `backend_a.worker_bridge.WorkerBridge.handle`：B実handlerの呼出・再配送・確定済み結果の復旧。
- `api.worker_app.create_worker_app(runtime, ai)`：明示注入による内部アプリ。
  Bの `/tasks/run` とAの既存設定 `/internal/jobs` を同じ認証付き処理へ接続。公開APIには追加しない。

各プロセスで同じFirestore/Storageを指すruntimeを構築して設定してください。
APIとWorkerがメモリ実装で別プロセスの場合、状態は共有されません。
Emulatorで別プロセスにする場合は、両プロセスに同じStorage Emulatorのhost/bucketを設定してください。
build_runtimeはloopbackのStorage Emulator指定を検査してSDKを構築し、無指定ならMemoryBlobsを使います。
別々のFirestore/Storageクライアントを持つAPI/Workerのテストでも、同じデモ環境を参照して検証しています。

## 保存形式（実装上の追加、既存契約のフィールドは変更しない）

- `rooms/{room_id}.current_round_id`：現在のラウンド。
- `round_lookup/{round_id}.room_id`：round_idだけのAPIから親roomを引くサーバー専用索引。
- `rounds/{round_id}/private/main`：
  - `players`: uid→role。ラウンド開始時の名簿。
  - `returned_uids`: 戻った人のリスト。次のゲームでも過去の閲覧権限を復活させない。
  - `config`: 開始時点のGameConfigのスナップショット。
  - `odai_text`: Bが選ぶお題。B未接続の場合はnull。
  - `outputs["0".."5"]`: 正本どおり `{text, asset_id}`。文字列キー。
  - `gesture`: session_id / finished / video_asset_id。
- `rounds/{round_id}/gesture_batches/{sequence_number}`：正本のGestureBatch。
  セッション開始前の送信、別セッション、finish後の送信は拒否。同じ連番は最初の値を保持。
  バッチのJSONは仮上限250KB。Firestore文書1MiB制約に収まるよう、PoCまでは安全側に制限。
  フロントの送信間隔・間引き方式は変更しない。調整が必要なら上限をB/フロントと確認する。
- `requests/{sha256(uid, action, request_id)}`：冪等な応答と内容の指紋。異なる内容で同じIDは400。
- `task_outbox/{task_id}`：Transactionと同時に記録した配送注文。外部送信はcommit後。
- `cleanup_outbox/{room_id}-{round_id}`：削除失敗時の再実行。
- `rounds/{round_id}/watchdog_checks/{check_id}`：期限タスク再配送による監視増殖の防止。
- `jobs/{job_id}` の追加内部情報：step_index / result / finalized_at / advance_pending。
- `progress_outbox/{round_id}-{job_id}`：確定済み結果からの進行再実行。AIの試行上限と独立。
- `execution_outbox/{round_id}-{job_id}`：実行中断の検出。payload / attempt / expires_at。
  合計3試行を使い切るまでは別名タスクを再登録し、使い切ったら失敗確定。

内部保存形式はGameJobIO/SinkでBの既存Protocolへ変換し、結合検証済みです。
本番Sinkの配置・設定統合はBとの確認が必要です。
モデルの引数を変えたり、座標JSONを配列形式へ変更したりしていません。

## 結果の確定と復旧（ローカル実装・検証済み）

1. payloadのjob_id、kind、step_index、revisionをDBのジョブと照合する。
2. 終了済みジョブは二重確定しない。古いラウンド・失敗済みゲームのメイン結果を反映しない。
3. 通常のジョブは対象のSTEP・進行を確認してoutputsとSTEP statusを同一Transactionで書く。
4. 生成画像はsave_asset完了後にそのasset_idをoutputsへ入れる。録画はAIに渡さない。
5. 類似度確定時はresult_status=readyとresult/finalを同一Transactionで記録する。
6. 成功結果・job done・advance_pending・progress_outboxを同時確定してからadvance_stepを呼ぶ。
   再配送時は推論を省略して進行だけを再実行。進行後の確認処理で落ちても同じ経路で復旧する。
   キューの再配送上限を使い切っていても、Aの保守処理/heartbeatがoutboxを実行する。
7. retryableと上限3回をBが管理し、fatal=TrueではROOM/roundをfailed、fatal=Falseでは
   gesture_ai_statusだけをfailedにする。Aのadvance_stepはAIの再試行を担当しない。
8. 推論前にexecution_outboxを記録。プロセス停止でhandle_jobが返らなくても、Aが実行期限で再配送/失敗確定する。
   3回目のwait_for timeoutはその場で失敗確定し、4回目のAI呼出を待たない。

## 接続の実装とBへの確認

- **お題**：初回ジョブでodai_text未設定ならBのFileOdaiSourceが選び、Transactionで1回だけ保存する。
- **revision**：メインはroundとjobのrevisionを照合。裏読み取りはjobのrevision・現在ラウンドを照合し、
  メインが進んだだけの結果を捨てない。追加の共有payloadフィールドはない。
- **遅い裏読み取り**：finished後も返却前ならprivateとresult/finalのgesture_ai_textを更新する。
  メインのSTEP・revision・締切は変えず、全員帰還後は反映しない。
- **保存失敗/不正出力**：未確定画像を後始末し、空のAI文章・不正スコア・参照不能画像を成功確定しない。
- **本番設定と担当**：get_settings/処理別provider/既存Bの環境変数名を互換接続した。
  `SERVICE_ROLE=worker` は `api.worker:app` で永続IO/Sinkを構築する。Bのworker.mainはLogSinkのまま保持。
  Dockerとdeploy_worker.shの入口は同じ役割選択に統一。本番採用とSinkの保守責任はBに確認する。
- **共有Storage/キュー担当/TTL**：backend-a-confirmation-response.mdにBへの回答と差異を記録。

## 時間・公開範囲の解釈

- 進行中の人Aに人Bの録画は公開しない（ユーザー承認済み、§6の表優先）。
- ジェスチャーSTEPのactive時に、countdown_seconds + record_secondsの期限を確定。
  gesture/startを遅らせても締切を延長しない。秒数は仮設定。
- 文章は空/空白を受け付け、保存内容を加工しない。未受信を空文章へ置換しない。
- is_autoは端末申告を記録。サーバーの受付期限はdeadline_at+猶予で判断。
- `leave` 後はphase=returned、全員帰還でphase=lobby。履歴権限はラウンド別returned_uidsで判定。
- 誰かが離脱して戻らない部屋の強制リセット・自動leave・ホスト移譲は追加しない。
- Security Rulesは公開状態だけを参加者に許可。resultも含めた中身はHTTP履歴API経由。
- 可視STEPのアセットでも、private.outputsが参照していない未採用アセットは公開しない。

## 外部検証の区別

Cloud SDKアダプターのモック検証、実Bコード+Firestore/Auth/Storage/RulesのEmulator検証、実環境検証を区別します。
具体的な実行結果はbackend-a-progress.mdに記録します。
実IAM、実キュー再配送、Cloud Run、Storage実保存、実Firebase token、実モデルは未検証です。

Firestore競合の再検証でSDKの5回再試行が尽きるケースを再現しました。
同一Transactionの読取をキャッシュします。2026-11-08の再現によりSDKの即時再試行を1回にし、
確認できたABORTEDだけを新Transaction+指数的full jitterで合計8回まで再試行する方式に変更しました。
これはエラーを409へ読み替える修正ではなく、新しいスナップショットで担当・未提出を再確認する修正です。
12同時提出×5回を含むEmulatorテストが成功しています。本番の競合時レイテンシは未検証です。

## 最新mainの保存期間・形式確認（2026-11-08）

生成画像は24時間保存へ決定済み。Storageの実体が自動削除された後は既存assets APIが404/ASSET_NOT_FOUNDを返す。
履歴・result/finalのJSONは維持し、認可は先に行うため参加者以外・帰還済みユーザーは403のまま。
画像の定期削除ジョブ・AIによる再生成・新しい公開フィールドは追加しない。Emulatorはlifecycleを動かさないため外部削除を模擬して検証する。
PNGはBの実測報告をmainから取り込んだ（image/png・PNG signature・約1.2MB）。PNG前提は維持し、実AIの再確認スクリプトは実行していない。


## G0の最新Bコード接続

6c45990のBコードを保持：429の6/12秒再試行、provider切替、座標の間引き/丸め、結論プロンプト調整。
AはBの実装を変更せず、I/O境界とジョブ確定を追加テスト。Manifestは最新mainのPython/お題ソースだけを記録する。
Bの同意とAの返答はab-coordination.md。runtime/入口/Storage/Tasks分担の未合意は解消し、実SA/URL/費用/配備の承認待ちを区別する。
