# AブランチPush・main起点のローカルマージ検証

## 最新追記：PR #2のmain更新取込（2026-11-08）

- origin/mainは82bf14e。Aへ取り込み、changelog1件の競合を両者の決定を残して解消。
- 画像24時間保存・BのPNG確認報告を反映。Storage lifecycle後の404と履歴維持の2テストを追加。
- 最新結果：オフライン118件/skip3件、Emulator121件、Rules5件、匿名3人の実HTTP一巡が成功。
- common/Worker/API公開契約の新たな変更なし（Storageの説明コメントのみ更新）。Bの実Workerを使用し推論だけモック。
- B確認スクリプトを実行せず、実環境・デプロイ・mainへのマージなし。Dockerは未検証。
- B画像のTasks/OIDC提案と残る運用値はteam-integration-guide.md参照。

以下は88fc796までの以前の試験記録。現在の対象main/テスト件数は上記を優先する。

2026-11-08。ユーザーの明示許可に基づき、Aブランチだけ通常Pushした。
mainへのPush/マージ・強制Push・PR作成・Google Cloud実環境操作は行っていない。

## 対象とGit操作

- 作業ブランチ：`codex/backend-a`。開始時HEAD `64eb82e`、作業ツリーはclean。
- Push前に126 tracked filesの不要物と、未Push履歴の148 blobsを秘密情報パターンで検査し、検出なし。
  実秘密鍵・Google APIキー・GitHub/AWS/Slackトークン・service-account JSONのパターン、
  .env/秘密鍵ファイル/.tools/.venv/node_modules/キャッシュ/ログの追跡混入を確認。
  gitleaksは未導入。パターン検査であり、未知の秘密情報まで完全に検出する保証ではない。
- 通常Push：`origin/codex/backend-a` を `afd375f → 64eb82e` に更新成功。
- その後read-only fetch。最新 `origin/main = aa9d9c5`、追加更新なし。
- `origin/main` から追跡なしの一時ローカルブランチ `codex/backend-a-merge-check-64eb82e` を作成。
- `git merge --no-ff --no-commit codex/backend-a` を実行し、テスト後に一時結果を `c983f49` で保存。
  この一時ブランチはPushしない。
- **今回の競合ファイルは0件**。mainは前回のedf835aでA側へ取り込み済みのため、取り込み直しによる競合はない。
  マージ結果のコードは `64eb82e` と一致することを確認した。
- 検証後 `codex/backend-a` へ戻った。ローカルmainは開始時と同じ `2184ead`。
  この検証記録と進捗の文書更新をAブランチに保存し、同名リモートへ通常Pushする。

## 共有ファイルと解決状態

今回は新たな競合解消や共有契約変更は不要。既存差分の詳細は shared-file-review.md。

| ファイル | 検証した統合内容 |
|---|---|
| common/enums.py | 状態文字列を維持したStrEnum。Job契約スキーマ照合成功 |
| common/models.py | JobPayload/JobResult/JobDoc/ErrorInfoはBのスキーマと一致。Aの入力検証/設定snapshotを維持 |
| common/settings.py | Bのget_settings/provider/GCP_PROJECT/STORAGE_BUCKET互換口とAのCloud opt-inを維持 |
| common/storage.py | AのAssetStorageとBの注入インターフェースを維持。録画のみ削除、失敗metadata保持、datetime保存 |
| Dockerfile | 共通イメージのSERVICE_ROLEでapi/worker/deadlinesを選択。非root、固定依存。Docker実行は未検証 |
| pyproject.toml | A/B依存とパッケージを包含。uv.lock検査・隔離環境の66パッケージ整合性・wheel導入が成功 |
| worker/main.py | main版と同じ。LogSink/MemoryJobIOはFirestoreへ書かない。永続入口はapi.worker:appへ分離 |

Bのworker/dataとmainのfrontendは変更していない。既存コードの削除なし。
`worker/main.py` 自体が永続化済みであるとは報告しない。

## テスト結果（実際のマージ結果上で実行）

| 検査 | 結果 |
|---|---|
| オフラインpytest | **116 passed / 3 skipped**（3.27秒）。skipはEmulator専用 |
| Auth/Firestore/Storage Emulator pytest | **119 passed**（23.64秒） |
| Firestore/Storage Security Rules | **5 passed** |
| 実HTTPの3人スモーク | **成功**。一時uvicorn、Emulator匿名認証3UID、B実Worker+MockAI、Firestore/Storage共有、最終履歴・帰還まで |
| B Worker → A進行 | 実handle_job/run_job、GameJobIO/Sink、write_job_result→advance_stepを検証 |
| Transaction/冪等性 | 同時提出、再送、二重配送、古いrevision、保存後/進行前停止からの復旧、遅い裏読み取りのテスト成功 |
| Python依存 | uv lock --check --offline / uv pip check成功 |
| wheel | build、別ディレクトリinstall、ソース外からAPI/永続Workerのオフライン起動成功 |
| フロント型 | A/B実応答・公開文書25例を再生成し、現行TypeScript型への代入検査成功 |
| 静的検査 | ruff check / format --check（41ファイル）、compileall、shell構文、git diff --check成功 |
| Docker | CLIは存在。ローカルdaemon socketなしでdocker info失敗。イメージbuild/runは未実行 |

Emulatorはdemo-gesture-relay/loopbackのみ。本番認証情報を除外して実施し、API/Emulator停止を確認。
Rulesの拒否ログは期待結果。JavaのUnsafe警告は出たが全検証は成功した。
ログは.tools/push-merge-validation.log（Git対象外）。

## 残るA/Bの確認・未検証

1. **永続Workerの入口・保守責任**：api.worker:app + AのIO/SinkをBのデプロイに採用するかレビュー。
   従来worker.main:appのままだとFirestoreには結果が残らない。
2. **Storageと入力制限**：録画のみの削除、画像保持/実ライフサイクル、PNG保証、座標上限、BのPython3.12環境。
3. **実キューとIAM**：キュー作成担当、配送SA/URL/OIDC、ゼロ台時を含むoutbox回復の稼働条件。
4. **チーム実機結合**：フロントの実Backend、ブラウザ購読、スマートフォンの録画・再生・ネットワーク。
5. **Dockerと実クラウド**：Docker環境での起動確認、実Auth/Firestore/Storage/Tasks/AI/Cloud Run等は未検証。

Git上の試験マージは競合なし、ローカルテストは成功。Docker/実環境まで検証済みとは扱わない。
ユーザーのmain禁止は継続。実際のmainへマージする操作は行わない。
