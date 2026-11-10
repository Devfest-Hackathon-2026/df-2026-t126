# B → A 確認事項

- 作成: 2026-11-07（B）
- 関連: [shared-types.md](shared-types.md)（型・関数）／[specification.md](specification.md)（仕様）／[changelog.md](changelog.md)
- 使い方: 答えが決まったら「状態」を `✅ 合意` に変え、「回答」に一言書く。決めた日時と理由は changelog にも残す。

| 状態 | 意味 |
|---|---|
| ⬜ 未確認 | A の回答待ち |
| ✅ 合意 | 決まった |
| 🔄 相談中 | 案が分かれている |

---

## 1. 先に決めたいこと（決まらないと進めない）

| # | 確認内容 | B の案・状況 | 状態 | 回答 |
|---|---|---|---|---|
| 1 | **Firestore を作るのは誰か** | 現在、API が無効（`Cloud Firestore API has not been used`）。リージョンは東京（`asia-northeast1`）、モードは Native の想定。**リージョンは作成後に変えられない** | ⬜ | |
| 2 | **使うプロジェクト** | `gesture-relay-game`（番号 `122800925175`）に統一。重複していた `-f6dc7`・`-d20ea` は削除済み。全員の招待（ライター権限）が、このプロジェクトで済んでいるか | ⬜ | |
| 3 | **Cloud Run のリージョンと構成** | 東京。API と Worker は**別サービス**の想定（構成図では未確定） | ⬜ | |
| 4 | **`advance_step(room_id, round_id)` の用意** | A の共有部品。人の提出（API）と、AI 完了後（Worker）の両方から呼ぶ。いつ頃できそうか | ⬜ | |
| 5 | **Cloud Tasks のキュー** | 役割表どおり、**キューの作成と権限は B、注文の生成・送信（`enqueue`）は A**。B が `gesture-jobs` を作成済み（東京・最大3回・5秒から60秒の間隔）。下の設定値と、`DEADLINE_URL` の決定をお願いしたい | 🔄 相談中 | |

---

## 2. 合意したいこと（shared-types.md §11）

| # | 項目 | 状態 | 回答 |
|---|---|---|---|
| 1 | §1 列挙型を `common/enums.py` に集約（実装済み） | ⬜ | |
| 2 | §2 `JOB_POLICY`（`gesture_read` だけ `fatal=False`） | ⬜ | |
| 3 | §3 結果の書き込みは Worker が直接行う（`run_job`・`write_job_result` は B、`advance_step` は A） | ✅ 合意（2026-11-07） | 構成図に合わせた |
| 4 | §3 結果の書き込み先（`private/main.outputs` のキー形式） | ⬜ | |
| 5 | §4 `delete_round_assets` を A が `leave` と `start` から呼ぶ | ⬜ | |
| 6 | §7 秒数を Firestore の `config/game` に置く | ⬜ | |
| 7 | §3 `ApiErrorCode` を A が別に持つ | ⬜ | |
| 8 | §4 `can_read_asset`（現在の入力素材／公開済み履歴）を A が実装し、履歴 API と assets API で共有 | ⬜ | |
| 9 | §4 録画の保存完了（Storage と `AssetDoc`）を確認してから人 C へ進む | ⬜ | |
| 10 | §1 `FailReason` を `communication_failed` / `player_dropped` に分ける | ⬜ | |
| 11 | §7 ハートビート（5秒・15秒）と、受付期限 `deadline_at + 5秒` | ⬜ | |

---

## 3. B の進捗（共有）

| 項目 | 状態 | 場所 |
|---|---|---|
| 共有の列挙型・モデル・設定 | 実装済み | `common/enums.py`、`models.py`、`settings.py` |
| AI クライアント（モック／本物） | 実装済み | `worker/ai/` |
| `run_job`（画像生成・ジェスチャー読み取り・結論・類似度） | 実装済み | `worker/jobs.py` |
| 再試行の判断（再試行は 500、確定は 200） | 実装済み | `worker/handler.py` |
| Worker の入口（Cloud Tasks が呼ぶ） | 実装済み | `worker/main.py`（`POST /tasks/run`） |
| `save_asset` / `delete_round_assets` | 実装済み。録画の保存にも使える | `common/storage.py` |
| 本物の AI（Vertex・キー不要） | 動作確認済み | 画像生成 約11秒、結論 約2秒、ジェスチャー読み取り 約6秒 |
| Storage バケット | 作成済み | `gesture-relay-game-assets`（東京・非公開・24時間で自動削除） |
| テスト | 12件合格 | `tests/` |

**A に影響する点**
- `save_asset(room_id, round_id, kind, step_index, data, content_type)` を、録画の保存にも使える。形式は `video/webm` か `video/mp4`。保存の完了後に `asset_id` が返る。
- 保存が失敗すると、`AssetError`（`code` は `UNSUPPORTED_MEDIA_TYPE` / `PAYLOAD_TOO_LARGE` / `INVALID_INPUT`）を投げる。API のエラーコードに対応させてほしい。
- アセットの記録（`AssetDoc`）は `rooms/{room_id}/rounds/{round_id}/assets/{asset_id}` に書く。

---

## 3-2. 決定したこと

| 日付 | 内容 | 影響 |
|---|---|---|
| 2026-11-08 | **生成画像の保存期間は、作成から24時間**（Storage の自動削除に任せる） | A の `delete_round_assets` は録画だけ削除のままで良い。画像は個別に消さない。バケット `gesture-relay-game-assets` は、全体に24時間の規則を設定済み |
| 2026-11-08 | **画像生成の混雑対策**（Vertex の画像モデルは1分あたりの上限が小さく、3件目で 429 が出た）。429 かタイムアウトのとき、`gemini-2.5-flash-image`（global → us-central1、約6秒）に順に切り替える。Gemini API（キー）への切り替えは、無料枠で画像生成の上限がゼロのため効かない（キーがあるときだけ試す）。実測: `gemini-3.1-flash-image` は global のみ | 実装は `worker/ai/real.py`（B担当）。A への影響なし。画質は旧世代モデルになるが、ゲームを止めないことを優先 |
| 2026-11-08 | **画像の絵柄は、写真風・細部が豊かなまま**（「イラスト風」に統一しない）。人Aが説明する材料が多く、伝言で情報が変わる面白さに合うため | プロンプトは `worker/prompts.py`（B担当）。A への影響なし |
| 2026-11-08 | **Vertex の画像生成は PNG で返る**（実測: `image/png`、中身も PNG、約1.2MB）。A の接続部の PNG 前提で問題なし | 変換処理は不要。20MB の上限にも収まる。モデルを変えたら再確認する（`scripts/check_image_format.py`） |

### Cloud Tasks の設定値（A の環境変数に入れる値）

| 環境変数 | 値 | 状態 |
|---|---|---|
| `TASKS_LOCATION` | `asia-northeast1` | ✅ 作成済み |
| `TASKS_QUEUE` | `gesture-jobs` | ✅ 作成済み（最大試行3回、間隔 5秒〜60秒、同時実行4） |
| `WORKER_URL` | `https://worker-122800925175.asia-northeast1.run.app/tasks/run` | 現在の Worker。**永続化つきに切り替えたら、再デプロイ後も同じURL** |
| `INTERNAL_AUDIENCE` | `https://worker-122800925175.asia-northeast1.run.app` | URLのベース部分 |
| `DEADLINE_URL` | 未定 | **A が決める**（締切を処理するサービス） |
| `TASKS_SERVICE_ACCOUNT` | 未作成 | 注文を送る専用アカウント。作成と権限は `docs/deploy-worker.md` §5 の手順 |

- キューの最大試行回数（3）は、`JOB_POLICY` の `max_attempts=3` と**必ず一致**させる（ずれると、失敗が確定せずゲームが止まる）。

---

## 4. 未決定（A・B 共通）

各段の秒数／リトライ間隔／安全フィルタ拒否後の扱い（`ai_blocked` は再試行しない案）／類似度の見せ方／Worker を API と同じサービスに置くか別にするか

---

## 5. 設定値（B の環境）

| 項目 | 値 |
|---|---|
| プロジェクト ID | `gesture-relay-game` |
| AI の呼び出し | Vertex AI（`global`）。認証は ADC（Cloud Run ではサービスアカウント） |
| Storage | `STORAGE_MODE=gcs`、`STORAGE_BUCKET=gesture-relay-game-assets` |
| Python | 3.12（`uv`） |

- API キー・認証情報は GitHub に置かない。開発中は `.env`（`.gitignore` 済み）、本番は Secret Manager。
