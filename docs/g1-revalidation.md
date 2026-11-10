# G1：フロント修正後のA側再検証

2026-11-08。作業ブランチ `codex/g1-validation-handoff`。
PR #3を基本実装とし、frontend/配下を変更しない合意に従う。

## 合意と対象

- [フロントの分担回答](https://github.com/trtrna/gesture-relay-game/pull/3#issuecomment-6718844380)
  / [Aの同意](https://github.com/trtrna/gesture-relay-game/pull/3#issuecomment-6718885506)
  / [修正完了・再検証依頼](https://github.com/trtrna/gesture-relay-game/pull/3#issuecomment-6718947640)。
- フロントは安全ガード、heartbeat、認証/購読エラー、MediaPipe skip、UI/カメラ/録画を所有。
  Aはfrontend/外のharness、Emulator/Worker/HTTP検証と資料を所有する。
- 取得したmainは `c8e2375`。PR #3 frontend `3db187b`、PR #4 frontend-effects `dd6794b`。
  フロントが取り込んだmain `3ce0242` より新しいBのお題/プロンプト等を保持した。
- 隔離したローカル結合：PR #3 + main = `3d9aefa`、PR #4 + main = `3111b29`。
  frontend/本体・既存scripts/config/package/lockは各PRの先端と一致。
  api/backend_a/common/worker/data、Docker、Python依存、Rulesはmainと一致。
  これらの検証ブランチはPushせず、実main/frontendを変更しない。

## 今回の修正

1. 以前の `frontend/tests/pr3-local-validation.mjs` を参考に、Aの別PR向けに
   **tools/validate_frontend.mjs** へ分離した。FRONTEND_ROOTで別checkoutを明示し、
   生成module/SDK解決用link/config/logはA側の.tools配下にだけ作る。補完adapterは導入しない。
2. 現行realBackendのdemo-project/loopbackガードを保ったまま実行。
   外部URL/socketもharness側で拒否。PythonはEmulator・AnonymousCredentials・MockAIだけ。
3. 現行 `startHeartbeat` を直接使用し、即時+5秒後、3人で合計6回のHTTP送信を確認。
4. 検証用moduleのonSnapshot境界にunavailable/permission-deniedを注入し、4購読×2種類を確認。
   unavailableは4つともonErrorへ、permission-deniedはroom/roundがnull、players/stepsは通知なし。
   signin/connectionのderiveViewもproblemへ遷移する。
5. Aの古い `docs/backend-b-source.json` がBの最新変更を検出し、初回Pythonが
   **1 failed / 138 passed / 3 skipped**。mainの13ソースと照合してdigest/出所revisionを更新。
   testの旧revision前方一致を40桁SHA検証に置換し、全ファイルdigestとJob schemaの検証は維持。
   Bの実装・データ・プロンプト自体は変更していない。

## 新規実行結果

| 検証 | 結果 |
|---|---|
| 修正後Python offline | 139 passed / 3 skipped（3.53秒） |
| Auth/Firestore/Storage EmulatorのPython | 142 passed（22.55秒） |
| Firestore/Storage Rules | 5 passed |
| PR #3 frontend tests | 14 passed（effects6、guard4、heartbeat4） |
| PR #4 frontend tests | 24 passed（effects16、guard4、heartbeat4） |
| 両フロントのlint/型/build | PASS。SKIP_MEDIAPIPE=1で通常mock buildとEmulator mode buildをそれぞれ実行 |
| PR #3と最新mainの3人HTTP一巡 | PASS。14 API、4購読、匿名3UID、PNG/MP4、401同一body再送、現行heartbeat、結果/退出 |
| PR #4と最新mainの3人HTTP一巡 | PASS。同じ境界を新規実行。ローカルcountdown=10秒のsnapshotも確認 |
| 購読エラー注入 | 各一巡で8ケース成功。画面状態モデル2ケースも成功 |
| A/共通/テストのruff check | PASS |
| A/共通/既存テストのformat | 42ファイル成功。新規Bのtests/test_odai.pyは既存format指摘のため別記 |
| worker込みruff | main由来B905/UP041/I001の3件が残る。Bコードは変更しない |

各一巡のrealBackend SHA256は
`392b46276f12e657a3bd137a33e82907d69adf87fd238bdf65e80e233dbced88`。
Node24の既存依存を利用し、フロントの直接依存13個はpackage-lockのversionと一致を確認。
新規npm ciやクリーンinstallの試験ではない。Node/シェル構文、git diff --checkも成功。
Emulator buildには500KB超chunkの警告がある。MediaPipeモデル取得は明示skipし、実Cloudへ接続していない。

## 限界・残条件

- **ブラウザDOM/React effect/実カメラ/MediaRecorder/実録画/iPhone/HTTPSはAでは未検証。**
  フロントのブラウザ成功報告は別担当の証拠であり、このAの新規テスト結果には足さない。
- onSnapshotへの注入はadapterの通知経路と状態モデルの検証。
  Firestoreの実障害でUIが表示された証明ではない。フロントでテスト用SDK mockから
  error callbackを呼び、Reactのproblem画面と再試行ボタンまで検証する方法を提案する。
- countdown=10はEmulatorだけのtest fixture。実config/gameは未照会・未変更で、採用は人間の判断待ち。
- 最新mainとのmergeで **docs/changelog.mdの競合が両PRに再発**。
  ローカルではフロントの16:45/14:08/12:00等とBの短文お題変更を両保持して解消。
  PR #4ではエフェクト11種の履歴も保持。元のPRにはAから反映しない。
- フロント担当がmainを再取得して取り込み、最新headを指定した後、必要な再テストをする。
- PR #3/#4のmainマージは未承認。実Cloud読取・実AI・Tasks/OIDC・本番Rules・lifecycle・デプロイも未検証/不許可。
- Bのlint3指摘とtest_odaiのformat1指摘は既存課題として共有する。全静的検査成功とは報告しない。

## 再現方法

Node24、ローカルvenv、cached Emulator/Javaと各ローカル依存を用意する。
frontend/のコードや.env.productionを変更・取得しない。既存の他人のprocessは停止しない。

```bash
# Aのcheckout rootから。frontendは対象PRの別checkoutを指す。
export FRONTEND_ROOT='/absolute/path/to/frontend-checkout/frontend'
export G1_PYTHON="$PWD/.venv/bin/python"
node tools/validate_frontend.mjs --prepare

# 事前にローカルCLIの空config領域/cached Emulatorを指定する。
# 以下のCLIは導入済みのもののみ。credentials/API keysを渡さずdemo project限定。
env -u GOOGLE_APPLICATION_CREDENTIALS -u FIREBASE_TOKEN \
  -u GEMINI_API_KEY -u GOOGLE_API_KEY -u GCLOUD_ACCESS_TOKEN \
  -u GOOGLE_OAUTH_ACCESS_TOKEN -u CLOUDSDK_AUTH_ACCESS_TOKEN \
  firebase emulators:exec --project demo-gesture-relay --only auth,firestore,storage \
  --config .tools/pr3-firebase.json 'bash tools/run_g1_emulator_checks.sh'

# 10秒案をローカルだけで検証する場合：G1_COUNTDOWN_SECONDS=10をCLIへ渡す。
```

既定9099/8080/9199が使用中ならprepareは専用39099/38080/39199を選ぶ。
生成した検証moduleだけのport置換を結果に記録する。今回の両試験は既定portのまま成功。
設定/生成module/APIログ/結果JSONは.tools内に保存し、秘密や生ログはGitHubへPushしない。
