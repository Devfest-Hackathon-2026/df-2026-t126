# 共有する型・関数名の一覧（バックエンド）

- 最終更新: 2026-11-08（実装に合わせて §3-3 / §5 / §7 を更新）
- 仕様書: [specification.md](specification.md)（ゲームとAPIの約束）／変更履歴: [changelog.md](changelog.md)
- 対象: バックエンドの **A（API窓口・進行管理）** と **B（AI呼び出し・お題）**、およびフロントとの境界になる型
- 状態: **Bの推奨案を採用（Aと要確認）**。Aと合意したら §11 に記入する
- 言語: Python 3.11 以降 / Pydantic v2。JSON・Firestore の項目名は `snake_case`
- 値は仕様書の値と**一字一句同じ**にする（綴りがずれると、エラーにならず値が空になる）

## 0. 読み方

| 印 | 意味 |
|---|---|
| 【共有】 | Aと合意が要る。変えるときは日時と理由を変更履歴に書く |
| 【B】 | Bの中で決める。変えてもAに影響しない |

置き場所の案（パッケージ名は仮）:

```
common/enums.py     # §1 列挙型
common/models.py    # §2〜4, §6 の型
common/storage.py   # §4 save_asset / delete_round_assets
common/settings.py  # §7
worker/ai/          # §5 AIClient（real / mock）
worker/prompts.py   # §8
worker/odai.py      # §9
data/odai.json
```

---

## 1. 列挙型【共有】

`common/enums.py` に集約し、A・B・Worker が同じ定義を読む。値は小文字の `snake_case`（役割だけ `A` / `B` / `C`）。

```python
class RoomStatus(str, Enum):
    waiting = "waiting"; playing = "playing"; finished = "finished"; failed = "failed"

class FailReason(str, Enum):
    ai_failed = "ai_failed"                    # メインのAI処理が3回失敗
    communication_failed = "communication_failed"  # 端末は生きているが、提出・録画が届かない
    player_dropped = "player_dropped"          # 生存確認が途絶（途中離脱）

class PlayerPhase(str, Enum):
    lobby = "lobby"; playing = "playing"; viewing = "viewing"; returned = "returned"

class Role(str, Enum):
    A = "A"; B = "B"; C = "C"

class StepActor(str, Enum):
    player = "player"; ai = "ai"

class StepType(str, Enum):
    image_gen = "image_gen"; text = "text"; gesture = "gesture"; conclude = "conclude"

class StepStatus(str, Enum):        # 人のSTEP
    waiting = "waiting"; active = "active"; done = "done"; timeout = "timeout"

class JobStatus(str, Enum):         # AIのSTEP・ジョブ・gesture_ai_status 共通
    pending = "pending"; processing = "processing"; done = "done"; failed = "failed"

class ResultStatus(str, Enum):
    pending = "pending"; processing = "processing"; ready = "ready"; failed = "failed"

class AssetKind(str, Enum):
    image = "image"; video = "video"
```

- 案a（共通モジュールに集約）を採用。各自が文字列リテラルを書く案bは、綴りのずれに気づけないため採らない。
- `waiting` と `done` は、人のSTEPとジョブの両方に出る。どちらの列挙型で読むかは、対象（`StepStatus` か `JobStatus`）で決まる。

---

## 2. ジョブ【共有】

### 2-1. 種別

```python
class JobKind(str, Enum):
    image_gen = "image_gen"        # お題・文章 → 画像
    gesture_read = "gesture_read"  # 座標 → 文章（裏のAI読み取り）
    conclude = "conclude"          # 最終画像 → お題と同じ形式の短文（〜している〇〇）で推測
    similarity = "similarity"      # お題とAIの結論の類似度
```

### 2-2. 注文票（Cloud Tasks で送る中身）

```python
class JobPayload(BaseModel):
    job_id: str
    kind: JobKind
    room_id: str
    round_id: str
    step_index: int | None = None  # similarity などは None
    revision: int                  # 古い結果で上書きしない用
```

- 入力データ（文章・座標・画像）は載せない。Worker が Firestore / Storage から読む。再配送されても同じ結果になり、項目を足しても壊れない。
- 回数（`attempt`）は Firestore のジョブ側に持つ。

### 2-3. ジョブの記録

```python
class JobDoc(BaseModel):           # rounds/{round_id}/jobs/{job_id}（サーバーのみ）
    kind: JobKind
    status: JobStatus
    attempt: int = 0
    max_attempts: int = 3
    last_error: ErrorInfo | None = None
    revision: int
```

### 2-4. 致命度（失敗したらゲームを止めるか）

```python
class JobPolicy(BaseModel):
    max_attempts: int = 3
    fatal: bool                    # 失敗確定でゲームを止めるか

JOB_POLICY: dict[JobKind, JobPolicy] = {
    JobKind.image_gen:    JobPolicy(fatal=True),
    JobKind.conclude:     JobPolicy(fatal=True),
    JobKind.similarity:   JobPolicy(fatal=True),
    JobKind.gesture_read: JobPolicy(fatal=False),   # 裏の読み取りは止めない
}
```

| 失敗確定したとき | 書き込み | 画面 |
|---|---|---|
| `fatal=True` | `jobs/...status = failed`、ROOM を `failed`（`fail_reason = ai_failed`） | 進行不可の失敗表示。ロビーに戻るまで履歴は全員が見られる |
| `fatal=False` | `jobs/...status = failed`、`gesture_ai_status = failed` のみ | 失敗表示を出すだけ。進行は止めない |

- 案a（コード内の表）を採用。値を変えるには再デプロイが要るが、一覧で見えて、種類を足しても1行で済む。

---

## 3. 結果の受け渡し【共有】

### 3-1. エラー

```python
class ErrorCode(str, Enum):        # ジョブ（AI処理）のエラー。値はS1のエラーコードと同じ大文字
    ai_failed = "AI_FAILED"
    ai_timeout = "AI_TIMEOUT"
    ai_bad_output = "AI_BAD_OUTPUT"   # 形式不正
    ai_blocked = "AI_BLOCKED"         # 安全フィルタで拒否（再試行しない）
    invalid_input = "INVALID_INPUT"   # 再試行しない

class ErrorInfo(BaseModel):
    code: ErrorCode
    message: str
    retryable: bool                # 再試行してよい失敗か
```

- `retryable` は `ErrorInfo` に持たせる。同じコードでも、状況で変えられる（案a）。
- API の `NOT_YOUR_TURN` などの HTTP エラーコードは、Aが別の列挙型（`ApiErrorCode`）で持つ。ここは AI 処理のエラーだけ。

### 3-2. 結果

```python
class JobResult(BaseModel):        # AI処理の戻り値
    ok: bool
    text: str | None = None        # 文章・結論
    asset_id: str | None = None    # 生成画像
    score: float | None = None     # 類似度
    error: ErrorInfo | None = None
```

### 3-3. AとBの境界

| 関数 | 担当 | 役割 |
|---|---|---|
**Worker が結果を直接 Firestore・Storage に書く**（システム構成図の矢印9に合わせる）。

| 関数 | 担当 | 役割 |
|---|---|---|
| `run_job(payload: JobPayload, *, ai: AIClient, io: JobIO) -> JobResult` | **B** | AIを呼んで結果を返す（AI呼び出しだけ。純粋に近い関数で、モックでテストしやすい） |
| `write_job_result(payload: JobPayload, result: JobResult) -> None` | **B**（Worker 内） | Transaction で `revision` と `job_id` を確認し、§3-4 の場所に結果・ジョブ状態・失敗を書く。生成画像は `save_asset` で Storage に保存 |
| `advance_step(room_id: str, round_id: str) -> None` | **A**（共有部品） | 次の段へ進める。人の提出の処理（API）と、AI完了後の Worker の両方から呼ぶ |

- Worker の1回の処理: `run_job` → `write_job_result` → 成功なら `advance_step`。
- `run_job` が使う入出力は `JobIO`（`worker/jobs.py`）。入力の読み出し（`load_odai` / `load_text` / `load_image` / `load_batches` / `load_conclusion`）と、生成画像の保存（`save_image`、`asset_id` を返す）。本番の実装は A の `GameJobIO`、テストは `worker/io_memory.py` のメモリ版。
- `handle_job(payload, attempt, *, ai, io, sink)`（`worker/handler.py`）が、再試行の判断（再試行する失敗は 500、確定は 200）と、結果の書き込み（`sink.write_job_result`）、成功後の進行（`sink.advance_step`）を行う。`attempt` は `X-CloudTasks-TaskRetryCount + 1`。
- 進行のルール（どの段の次が何か）は A の `advance_step` に1か所だけ置く。Worker は進行のルールを持たない。
- Worker は API と同じリポジトリの Python なので、`advance_step` を import して呼ぶ（別サービスでも同じコードをデプロイする）。

**Cloud Tasks への返し方**
- 再試行する失敗（`retryable=True` かつ `attempt < max_attempts`）: HTTP 500 を返す（Cloud Tasks が再配送）
- 成功、再試行しない失敗、再試行の上限到達: HTTP 200 を返す（結果は `write_job_result` で書く）

### 3-4. 結果の書き込み先

| 場所 | 内容 |
|---|---|
| `steps/{step_index}.status` | 公開側。状態だけ |
| `private/main.outputs["{step_index}"]` | 秘密側。`{ "text": str \| None, "asset_id": str \| None }` |
| `result/final` | `odai`、`final_image_asset_id`、`ai_conclusion`、`similarity`、`gesture_ai_text` |

- キーは文字列（Firestore のマップキーは文字列のため）。

---

## 4. アセット（画像・録画）と削除【共有】

```python
class AssetDoc(BaseModel):         # rounds/{round_id}/assets/{asset_id}（サーバーのみ）
    kind: AssetKind
    path: str                      # 例: rooms/{room_id}/rounds/{round_id}/videos/{asset_id}.mp4
    content_type: str              # 実際の形式（例: video/mp4）。取得時はこの値で返す
    size_bytes: int
    step_index: int                # このアセットを作ったSTEP（権限の判定に使う）
    created_at: datetime

VIDEO_EXTENSIONS = {"video/webm": "webm", "video/mp4": "mp4"}   # 許可リスト兼、拡張子の対応表

def save_asset(room_id: str, round_id: str, kind: AssetKind, step_index: int,
               data: bytes, content_type: str) -> str:   # asset_id を返す
    # 拡張子は content_type から決める（.webm 固定にしない）
    ...

def can_read_asset(uid: str, round_id: str, asset_id: str) -> bool:   # A が実装
    # 「現在の入力素材」か「公開済み履歴」のどちらかなら True
    ...

def delete_round_assets(room_id: str, round_id: str) -> int:   # 消した件数を返す
    ...
```

- `asset_id = uuid4().hex`。パスは `AssetDoc` に保存する（案a）。権限確認も削除も、`asset_id` からすぐ引ける。
- 録画（A側のアップロードAPI）も、同じ `save_asset` を使う。
- 録画の保存先: `.../videos/{asset_id}.{ext}`（`ext` は実際の形式。`webm` か `mp4`）。画像は `.../images/{asset_id}.png`。
- 保存は、Storage への書き込みと `AssetDoc` の記録が**両方終わってから**完了とする。人Cの段へ進めるのは、その後（仕様書 §5）。
- `can_read_asset` は、履歴API と assets API の両方から同じ関数で呼ぶ（仕様書 §6）。

**削除の呼び出し役（3段構え）**

| タイミング | 呼ぶ人 |
|---|---|
| 全員がロビーに戻ったとき | **A**（`leave` の処理から） |
| 次のゲーム開始時（前ラウンドの録画が残っていたら） | **A**（`start` の処理から） |
| 作成から24時間後 | インフラ（Storage のライフサイクル設定） |

- 削除に失敗しても、ゲーム進行は止めない。取り残しは、24時間の自動削除で消える。
- 保存の失敗は `AssetError`（`code`: `UNSUPPORTED_MEDIA_TYPE` / `PAYLOAD_TOO_LARGE` / `INVALID_INPUT`）で返す。API のエラーコードに対応させる。
- 実装の正本は A の `common/storage.py`（録画のみ削除、失敗時は記録を保持、Timestamp 保存）。画像は24時間の自動削除に任せる（2026-11-08 決定）。

---

## 5. AIクライアント【B】

```python
class AIClient(Protocol):
    async def generate_image(self, prompt: str) -> bytes: ...
    async def read_gesture(self, batches: list[GestureBatch]) -> str: ...
    async def conclude(self, image: bytes) -> str: ...
    async def embed(self, text: str) -> list[float]: ...

def cosine(a: list[float], b: list[float]) -> float: ...   # AIを呼ばない別関数
```

- 実装は `RealAIClient` と `MockAIClient` の2つ。`AI_MODE` で切り替える。
- モックは固定の文章とダミー画像を返し、待ち時間を設定で足せる（本物は遅いため）。
- 類似度の式を後から変えやすいよう、`embed` と `cosine` は分ける。

**実装メモ（2026-11-08 時点の `worker/ai/real.py`）**
- 429（上限超過）のとき、呼び出しの中で待って再試行（6秒、12秒）。
- それでも 429 なら、もう一方の provider に切り替えて1回だけ試す（Gemini API は `gemini_api_key` があるときだけ。切り替え先では待たない）。
- 画像生成だけ、429 かタイムアウトのとき、`gemini-2.5-flash-image`（global → us-central1）に順に切り替える。`gemini-3.1-flash-image` は global のみで使える（実測）。
- 生成画像は PNG で返る（実測）。A の接続部の PNG 前提で問題なし。
- ジェスチャー座標は、AIに渡す前に `worker/ai/preprocess.py` で最大60サンプルに間引き、小数3桁に丸める（入力契約・API は変えない）。
- 上の再試行・切り替えの設定値は `Settings` に持たせず、`real.py` の中の定数にしている（A と共有する契約を増やさないため）。

---

## 6. 座標の型【共有（フロントとの境界）】

```python
class Landmark(BaseModel): x: float; y: float; z: float
class Hand(BaseModel):
    handedness: Literal["Left", "Right"]
    landmarks: list[Landmark]          # 検出した手ごとに21点
class Sample(BaseModel):
    timestamp_ms: int
    hands: list[Hand]
class GestureBatch(BaseModel):
    gesture_session_id: str
    sequence_number: int
    mirrored: bool
    samples: list[Sample]
```

- S1 の JSON 例と同じオブジェクト形式（案a）。重ければ PoC で `[x, y, z]` の配列に切り替える。
- エフェクトに関する項目は含めない（フロントの描画のみ）。

---

## 7. 設定値【共有（秒数）／B（AI関連）】

```python
class Settings(BaseSettings):          # 環境変数から読む（デプロイ時に固定）
    ai_mode: Literal["mock", "real"]
    # AIの呼び出し先は処理ごとに選べる（Vertex と Gemini API の併用のため）
    provider_image: Literal["vertex", "developer"]
    provider_read: Literal["vertex", "developer"]
    provider_conclude: Literal["vertex", "developer"]
    provider_embed: Literal["vertex", "developer"]
    gcp_project: str                   # Vertex 用。認証はキーではなく実行アカウント（ADC）
    vertex_location: str = "global"
    gemini_api_key: str | None = None  # Gemini API 用。Secret Manager から環境変数に入れる
    model_image: str
    model_read: str
    model_conclude: str
    model_embed: str
    ai_timeout_s: int
    max_attempts: int = 3
    video_max_bytes: int = 10_000_000
    allowed_video_types: list[str] = ["video/webm", "video/mp4"]   # 拡張子は VIDEO_EXTENSIONS で決める
    asset_ttl_hours: int = 24
    deadline_grace_s: int = 5          # 受付期限 = deadline_at + この秒数
    heartbeat_interval_s: int = 5      # 端末が生存確認を送る間隔
    dropout_after_s: int = 15          # この秒数、生存確認が途絶えたら離脱とみなす
```

**各段の秒数は Firestore の `config/game` に置く**（再デプロイせず、試しながら変えられる。案a）。

```python
class GameConfig(BaseModel):           # config/game（サーバーのみ書き込み）
    text_seconds: int
    countdown_seconds: int
    record_seconds: int
```

- 秘密のキーは Settings に入れず、Secret Manager から読む。
- モデルIDは設定値。利用可否・料金・クォータは PoC で確認してから固定する。
- 秒数の値は未決定（全体を作ってから決める）。

---

## 8. プロンプト【B】

```python
class Prompts(BaseModel):
    image_from_odai: str       # お題から最初の画像
    image_from_text: str       # {text} を埋め込む
    image_from_empty: str      # 文章が空のとき
    gesture_read: str
    conclude: str

def build_image_prompt(text: str, p: Prompts) -> str:
    # 空・空白のみなら image_from_empty を返す
    ...
```

- `worker/prompts.py` に定数で置く（案a）。文言を変えたときの差分が Git で見える。
- 空の文章は、保存はそのまま（Aは加工しない）。判定はプロンプトを作る関数が行う。
- `conclude` と `read_gesture` の出力は、最初は文字列。不安定なら JSON（`{"answer": "犬"}`）に切り替える。

---

## 9. お題【B】

```python
class Odai(BaseModel):
    odai_id: str
    text: str
    category: str
    difficulty: int
    subject: str | None = None   # 名詞（例: いぬ）。text = action + subject
    action: str | None = None    # 動作（例: 走っている）

class OdaiSource(Protocol):
    def select(self) -> Odai: ...      # 後でAI生成に差し替え可能
```

- 最初は `data/odai.json` を読み込む実装。お題を足すにはデプロイが要るが、準備は不要。
- **お題は「〜している〇〇」の短文**（例: 走っているいぬ）。動物・キャラクター・ものだけで、本物の人物は入れない（画像生成の安全フィルタに当たりにくくするため）。`text` は文字列のままなので、A の `odai_text` とフロントの表示に契約の変更はない（2026-11-08 決定）。
- 類似度は、これまでどおり**文全体で1つの点数**（`similarity`）。短文は、無関係でも点が高め（目安 0.6〜0.7）に出るため、**画面では点数そのものより、「おしい／近い／遠い」のような帯で見せる**ことを推奨（帯の境界は、実測してから決める。フロントの判断）。

---

## 10. 命名規則

| 対象 | 規則 | 例 |
|---|---|---|
| クラス | PascalCase | `JobPayload` |
| 関数・変数 | snake_case | `run_job` |
| 列挙型の値 | 小文字 snake_case（役割は `A` / `B` / `C`） | `communication_failed` |
| ジョブのエラーコード（値） | 大文字 snake_case（S1 に合わせる） | `AI_FAILED` |
| ID | `str`（Firestore の自動ID。`asset_id` は `uuid4().hex`） | `room_id` |
| 時刻 | UTC の `datetime`（JSON では ISO 8601） | `created_at` |

---

## 11. 合意状況・要確認

| # | 項目 | 状態 | 確認先 |
|---|---|---|---|
| 1 | §1 列挙型を `common/enums.py` に集約 | Bの推奨案 | A |
| 2 | §2 `JOB_POLICY`（`gesture_read` だけ `fatal=False`） | Bの推奨案 | A |
| 3 | §3 Worker が結果を直接書く（`run_job` と `write_job_result` は B、`advance_step` は A の共有部品） | **Aと合意済み**（2026-11-07）。構成図に合わせて変更（旧: A の `apply_job_result`） | — |
| 4 | §3 結果の書き込み先（`private/main.outputs` のキー形式） | Bの推奨案 | A |
| 5 | §4 `delete_round_assets` を A が `leave` と `start` から呼ぶ | Bの推奨案 | A |
| 6 | §7 秒数を Firestore の `config/game` に置く | Bの推奨案 | A |
| 7 | §3 の `ApiErrorCode` を A が別に持つ | Bの推奨案 | A |
| 8 | §4 `can_read_asset`（現在の入力素材／公開済み履歴の2条件）を A が実装し、履歴APIと assets API で共有 | レビュー指摘の修正案 | A |
| 9 | §4 録画の保存完了（Storage と `AssetDoc`）を確認してから人Cへ進む | レビュー指摘の修正案 | A |
| 10 | §1 `FailReason` を `communication_failed` / `player_dropped` に分け、`video_missing` は廃止 | レビュー指摘の修正案 | A |
| 11 | §7 ハートビート（`heartbeat_interval_s` / `dropout_after_s`）と、受付期限 `deadline_at + deadline_grace_s` | レビュー指摘の修正案 | A・フロント |

決定済み: 生成画像は作成から24時間で自動削除（Storage のライフサイクル。2026-11-08）。録画は、全員がロビーに戻ったとき・次のゲーム開始時にも削除する。

未決定（仕様書 §8 と同じ）: 各段の秒数、リトライ間隔、安全フィルタ拒否後の扱い（`ai_blocked` は再試行しない案）、類似度の見せ方
