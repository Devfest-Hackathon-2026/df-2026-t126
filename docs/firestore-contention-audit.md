# A：Firestoreの同一プロセス内競合修正

**最新の最終監査は末尾。コードは同じ8行の修正を維持し、検証・性能計測を追加した。**

main 150df95起点。B/フロント/共有型/ゲームルール/SDKの分散transaction条件は変更しない。

PR #7の追加検証中に、既存test_concurrent_submissions_are_committed_once[4]がEmulatorで失敗。
12提出中1件202・3件409・8件500となり、FirestoreのTransaction lock timeoutで8回のretryを消費した。
当時のFirestoreStoreはmainと同一。保守の新規ケースは成功していたが、全体は1 failed/160 passed。

## 修正と影響

FirestoreStoreごとのRLockで、同一process内のpure transaction callbackを1つずつ実行する。
複数readerが同じdocのwriteへupgradeする競合をローカルで抑える。MemoryStoreも既に同じ方式。
Firestoreの実transaction、fresh snapshot、8回のbounded ABORTED retry、business errorの扱いを維持。
別process/別instanceの競合には引き続きFirestoreのtransaction検証が必要であり、本lockで代用しない。

API/Workerの1つのStoreのatomic操作が直列化されるため、同一instanceの処理量とのtradeoffがある。
callback内に外部side effectを置かない既存前提を維持。実環境のthroughput/多instance負荷は未検証。

## 検証範囲

- 既存の5回×12並行提出のテストをそのまま利用し、期待値を緩めない。
- 既存のABORTED fresh transaction/8回上限/noncontention非retryテストも維持。
- この修正とPR #7保守変更の組合せはEmulator161/Rules5・3人ゲーム成功。
  修正単体もmain150df95基準の別worktreeで**Emulator142 passed（9.97秒）/Rules5 passed**。
  5回×12提出を含む全suiteと14 API/B MockAI/3人プレイが新規成功。SDK retry条件の既存テストも成功。
- これは実Cloudの再現試験ではない。SDK/IAM/負荷/遅延の実値を確認したとは扱わない。

マージは人間の個別承認待ち。#3は通常の3人一巡では成功済みだが、本同時提出リスクを承認前に共有する。

## PR #8 最終監査

### 対象

- main `150df957f6aa11cb75e8d5b383791577a7f0e23e`。
- 検証実装head `875fdeabb768ad4168635dcbc7063411c67b9b26`（以後の結果記録/require-correct追加も同じStore実装）。
- 修正後Store SHA256 `d4c106290b6cb2de57d20157fde09ba06842af421fe7f9e0e2cf45f71b544c7c`。
- 比較用main Store SHA256 `383b303e3deeada2cbe637cc872439a807dc96d1044b809c0cbf6173336b2ce1`。
- #3 `93717e1`、#4 `47fc72e`、#7 `1329740c39227879f70c6a9c6b8db3bf2997c3fb`。
  frontendは#3＋mainのローカル結合 `a36ea00`（製品frontendは93717e1と一致）を読み取り参照。
- #7併用は隔離branchの `148dca77a3a1cd4bf2c1007f59da0f6925c9f681`。
  main/source owner branchを更新せず、#7も実mergeしない。

### ロックと安全性

- `atomic()`のwithがSDK処理・callback・commit・再試行を囲む。解放専用の手動コードはなく、例外でwithを抜ける。
- RuntimeError/業務ApiError/ABORTED枯渇/SystemExit後に、**別スレッド**が次のtransactionを実行する4ケースを追加。
  同じthreadのRLock再取得で取り忘れを見逃さない。別Storeをブロックしない1ケースも追加。
- 元mainのatomic本体と新しい_atomic本体はAST一致。8回・7回sleep・ABORTED/そのcauseだけ再試行・fresh transaction・
  非競合例外を再試行しない条件は既存テストでも維持。
- 動画decode/Blob IO/Tasks送信は既存コードどおりatomic外。callbackで別threadの同Store処理を待つような使い方は避ける。
- 排他範囲は**同一Storeインスタンス**。同じprocessでも別Store、別process、別Run instanceには共有されない。
  Firestoreの分散transactionを維持するが、多instanceの性能/安全をこのテストだけで保証しない。
- retryのsleepやSDK待ちもlock内。明示的なlock待ちtimeout/FIFO保証はなく、遅いtransactionによるhead-of-line blockingは残る。

### 今回の新規テスト

| 対象 | 結果 |
|---|---|
| #8単体 offline | 144 passed / 3 skipped（3.56秒） |
| #8単体 Auth/Firestore/Storage Emulator | 147 passed（9.89秒） |
| #8単体 Firestore/Storage Rules | 5 passed |
| #7併用 offline | 163 passed / 3 skipped（5.59秒） |
| #7併用の新規独立Emulator | 166 passed（12.81秒） |
| #7併用 Rules | 5 passed |
| それぞれの実HTTP一巡 | 14 API、4購読、匿名3UID、B実handler/jobs+MockAI、PNG/MP4送受信・終了/退出、401再送がPASS |
| 同時提出 | 各suiteの5回×12提出を維持。毎回202が1件、409が11件、STEP確定1回。期待値変更なし |
| 静的検査 | A/共通/テスト/計測ツールのruff・format44ファイル、併用48ファイル、git diff検査成功 |

workerの既存Ruff3指摘（B905/UP041/I001）、Bのtest_odai format1指摘は残る。全repoの静的検査成功とは報告しない。
秘密の代表パターンと不要生成物をPush前に検査。完全な秘密検出保証ではない。

### 実行中に起きた失敗を残す

1. 初回147件は145 passed/2 failed。計測用PROJECT_ID/ENABLE_CLOUDを全suiteへ渡したため、alias/環境未opt-inのテストが失敗。
   runnerの環境を分離し、テスト/期待値を変えず単体147件を成功させた。
2. 同じEmulatorでWeb購読一巡後に併用suiteを続けると、fixtureのclearDataがHTTP499（165 passed/1 error）。
   Emulator logはclearData→ListenStreamのキャンセル済み通知→CANCELLEDを記録。
   併用suiteと性能計測をそれぞれ新しい専有Emulatorへ隔離し、strictな166件を成功させた。
   testsをskip/xfailにせず、リセット/Watchのライフサイクル競合を既知のテスト基盤制約として残す。

### 修正前後の計測

同じローカルFirestore Emulatorでbefore→after各3組、各12提出、8並列（最初の8件をbarrierで同時開始）。
test HarnessのLocalAuth/MemoryTasksと完了fixtureを使い、提出だけを測る。実AI/実Auth latencyは含まない。
各組で専有demo DBをリセット。ログはstatus/時間/例外型のみで、入力・UID・tokenは出力しない。

| 指標 | 修正前 main | 修正後 #8 |
|---|---|---|
| 正しい組数 | 3/3（36提出） | 3/3（36提出） |
| 各組の応答 | 202×1、409×11 | 202×1、409×11 |
| 12件一組の時間 | 2.153〜4.308秒 | 45.8〜49.4ms |
| HTTP呼出開始からの平均応答 | 1,887.1ms | 24.9ms |
| 最大HTTP応答 | 4,307.3ms | 38.8ms |
| admission lock待ち | lockなし（比較不能） | 平均13.0ms、最大27.4ms |
| lock保持最大 | 対象なし | 5.3ms |

今回のbeforeも成功しており、**この36件だけでは成功率の改善を主張しない**。
過去の500再現と今回のread/write競合遅延の両方を判断材料とする。3組・固定実行順・warm Emulatorの小規模測定で、capacity推定に使わない。

別途、競合しない20ms待ちcallbackを24件/8並列で実行した**非DBの合成対照**では、
before 0.0816秒、after 0.6710秒（約8.2倍）。afterの待ち最大209.0ms。
独立処理を並列化できなくなるコストは実在する。これはCloud/Firestore throughputの実測ではない。

### 評価・判断

G1の単一Store・3人ゲーム用途では、実測した12提出burstの待ちは5秒heartbeat間隔に対して小さく、
例外解放/冪等性/全suiteの結果と合わせ、**PR #8のマージを推奨（個別承認待ち）**。
ただし単一Storeでの多数部屋・遅いSDK/障害時・長期公平性は未評価。無競合controlの約8倍低下を許容しない用途では、
部屋単位のadmission等を別途設計/測定すべきで、この結果を本番scale承認に使わない。

実Cloud、複数instanceの競合/throughput、実機カメラ/ブラウザUI、Docker実buildは未検証。
#8のReadyはコード統合準備を意味し、Cloud操作や実mergeの承認ではない。

### 再現と次の順序

専有demo Emulator、既存ローカル依存/Node24/venvを用意し、#8単体と#7併用を**別の新規Suite**で実行する。
RUNTIME_MODE/ENABLE_CLOUD/PROJECT_ID等は全pytestへ固定注入せず、設定テストが自身で変更できる環境にする。

```bash
# emulators:exec --project demo-gesture-relay --only auth,firestore,storage 内で
bash tools/run_g1_emulator_checks.sh

# 性能はWatch購読のテストと別の新規Firestore Emulatorで実行。
RUN_FIRESTORE_EMULATOR_TESTS=1 python tools/profile_firestore_contention.py \
  --checkout /absolute/path/to/main-checkout --repeats 3 --output .tools/profile-before.json
RUN_FIRESTORE_EMULATOR_TESTS=1 python tools/profile_firestore_contention.py \
  --checkout . --repeats 3 --require-correct --output .tools/profile-after.json
```

結果JSON/ログは.tools内。これは専有demo DBを消去するテスト用ツールで、共有Emulatorへ接続しない。
次は#8個別承認/merge→フロント担当が最新mainへ#3を追従→#3最終検証/個別承認→#4 base main変更/検証→#7最終調整。
フロント所有branchへ直接Pushせず、#7の実mergeも今回行わない。

## 最新main取り込み後の最終再実行

上記初回監査後、mainに3コミットが追加されたため取り込み直した。
最新基準は `7e4b4eb1c5d008bdf7718fbb39f089532b334935`。
`0a48a8f` は人間選定のお題41→44件、`8ac1331` はB実験の録画時刻修正、
`7e4b4eb` は前処理比較スクリプト/実験記録。すべて保持し、実AI実験スクリプトは実行しない。

お題更新直後は由来manifestが旧hashのままで、offline単体143 passed/1 failed/3 skipped、
併用162 passed/1 failed/3 skipped、単体Emulator146 passed/1 failedを検出した。
B由来13ファイルをorigin/mainのblobとバイト単位照合し、お題だけが変わったことを確認して
`docs/backend-b-source.json` のrevision/previous_revision/odai hashを更新した。
検証条件を弱めず、Worker/共有schema/お題そのものは変更していない。
その後の2つのmain追加は13ファイルを変更していないため、由来は0a48a8fのまま保持。

| 最新基準での対象 | offline | 新規専有Emulator | Rules | 実HTTP3人一巡 |
|---|---|---|---|---|
| #8 `e36d65cbf97851109ca9934b924a206b72dc74f5` | 144 passed / 3 skipped（3.49秒） | 147 passed（9.78秒） | 5 passed | PASS |
| #7+#8 `d2208ee66e6f68dfcad2f0dc134a4f276e525be3` | 163 passed / 3 skipped（5.41秒） | 166 passed（12.26秒） | 5 passed | PASS |

両方14 API/4購読/3匿名UID/B実handler+MockAI/PNG・MP4/終了・退出/401再送を新規実行。
各5回×12並行提出を含む。frontend参照はa36ea00、realBackend SHA256は
`392b46276f12e657a3bd137a33e82907d69adf87fd238bdf65e80e233dbced88`。
ログは各worktree `.tools/pr8-main7e-offline.log` / `.tools/pr8-main7e-final.log`。

以後は監査文書だけを追記。Store/テスト/計測コードは上記検証対象と同一。
性能のbefore/afterは初回150df95基準の値を保持し、7e4b4ebで再計測した値とは扱わない。
追加mainはStore/Worker/API/Rules/テスト/依存関係を変更していない。
推奨は変わらずG1単一Store/3人用途への#8統合（人間の個別承認待ち）。
正式レビュー数・CI実行数・Ready状態・公開headは最終GitHubコメントに記録する。

### 文書のみのmain更新への追従

main `6f1efa4c883310e97a4f374a94fedb17d30804c0` はBの実験文書17行追記だけ。
取り込み後と検証済みc14c3ddの差は `docs/gesture-experiments.md` のみで、
製品コード/全テスト/依存関係/Rules/設定/お題データは同一。
全Emulatorの再実行はせず、上記147/166・各Rules5・3人一巡の結果を同一コードへの証拠として保持する。
今回新規の追加確認はロック安全性5件（0.18秒）とgit diff検査の成功。
正式レビュー0件/CI0件という既知状態を成功CIと取り違えず、公開headはGitHub最終コメントを参照。
