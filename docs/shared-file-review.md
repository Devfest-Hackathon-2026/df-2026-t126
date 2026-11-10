# 共有ファイルの差分レビュー（A・B向け）

**最新追記**：main 82bf14e取り込みでchangelogのみ競合。Aの秒数追加とBの画像24時間決定を両方維持。common/・Workerに新たなコード競合なし。

2026-11-08。read-only fetch後のorigin/mainは `aa9d9c5`、Aの取り込み済みコミットは `edf835a`。
`git merge-base --is-ancestor origin/main HEAD` 成功。最新mainは既にAブランチの祖先で、未取込コミットなし。
このため今回の追加マージ・別結合ブランチは不要。ローカルAはリモートAのafd375fより新しく、上書きしていない。
その後、ユーザー指示でmain起点の一時ブランチでも試験マージし、競合0件・全ローカルテスト成功を確認。
詳細は [マージ検証記録](backend-a-merge-validation.md)。
下表は**Gitの未解消競合ではなく、mainへ共有する際にレビューが必要な既存差分**。

| ファイル | mainとの差 | 結合状態・確認事項 |
|---|---|---|
| common/enums.py | mainのstr+Enumに対しAはPython3.11のStrEnum | 状態名・値は同じ。Jobスキーマ照合済み。Python3.11以上が必要 |
| common/models.py | AはGameConfigと座標入力検証を追加。JOB_POLICYの表現差 | JobPayload/JobResult/JobDoc/ErrorInfoのJSONスキーマはB版と一致。gesture_readのみ非致命的。座標制限は下記参照 |
| common/settings.py | Aの安全なruntime切替とBのget_settings/provider/モデル設定を統合 | BのGCP_PROJECT/STORAGE_BUCKETを互換化。自動.env読込なし。cloudは明示opt-in、local/emulatorはmock限定。環境変数の配布方法をBが確認する |
| common/storage.py | AのAssetStorage/Transaction注入にBのconfigure/index/blobの互換口を追加 | 録画のみ削除、失敗時metadata保持、datetime保存。画像は24時間のStorage lifecycleで自動削除（最新mainで決定済み、実設定はB報告）。Bの既存storageテストは画像保持の期待値だけ承認方針に合わせた |
| Dockerfile | BのWorker専用Python3.12/uv入口に対し、AはPython3.11/pip固定依存・非root・役割選択 | SERVICE_ROLE=workerで永続IO/Sinkへ接続。既定api。実Cloudは安全ガードにより無設定では起動しない。Docker build/runはdaemonなしで未検証。Bの3.12環境との両対応は別途確認 |
| pyproject.toml | FastAPI/Auth/Tasks/録画依存、dev依存、パッケージ対象、固定lockを統合 | uv.lockとrequirements.lockを同期し隔離環境で検証。Bのworker.aiとdata/odai.jsonもwheelに同梱。配布名はgesture-relay-backend-aのまま（mainはgesture-relay-game）。変更が必要ならBとレビュー |
| worker/main.py | **差分なし（main版そのまま）** | LogSink/MemoryJobIOの入口。永続Workerはapi.worker:appに構成を分離。Bのhandler/jobs/AI/お題内部も無変更 |

今回の新しい共有契約変更は、ユーザー承認済みのmy-inputの2項目追加のみ。
共通Jobモデルの引数・JSON、run_job→write_job_result→advance_stepの契約は変更していない。
元のworker/dataとmainフロントについて `git diff origin/main -- worker data frontend` は空。

## B・フロントにレビューを依頼する入力制限

Aに以前からある検証は、21点/hand、最大2hands、有限数値、非負timestamp/sequence、最大1000samples/batch、
JSON250KB/batch、text2000文字、video10MB。うち具体的な上限値は運用上の仮値を含む。
B版の緩いPydanticモデルより厳しいため、B/フロントの実際の送信が範囲内か確認する。
座標の間引き・送信間隔・JSON構造はAでは変更しない。超える必要があれば上限変更案を共同確認する。
既存の共有Job契約のスキーマ一致だけで、全ての受入条件が同じと主張しない。

## Bへのレビュー依頼

1. 永続Worker起動先、IO/Sinkの配置・保守、環境変数配布を確認する。
2. leave/startは録画だけ削除、画像は24時間のStorage lifecycle（決定済み）。実配備時にB報告の設定を確認する。
3. キュー作成担当、配送SA/URL/OIDC、保守処理の稼働条件を確認する。
4. PNG形式はBの実測報告を82bf14eで確認済み。モデル変更時に再確認。BのPython3.12/実SDK環境の配備検証は別途行う。

ユーザー許可でAブランチだけ通常Push済み。本番接続・本番認証情報使用・デプロイ・PR/mainマージは未実行。
