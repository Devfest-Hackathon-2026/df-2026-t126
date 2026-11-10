# S1 データ・API の取り決め（仕様書）

- バージョン: **v2.2**（案）
- 最終更新: 2026-11-07 17:34 JST
- 変更履歴: [changelog.md](changelog.md)
- バックエンドで共有する型・関数名: [shared-types.md](shared-types.md)
- 位置づけ: 「S1 データ・APIの取り決め」(11/7) と「技術設計と未決定事項」(11/7) をベースに、チーム会議で決まったゲーム仕様を反映した仕様書。チームで合意したら決定ログに記入する
- 「未決定」と書いた箇所は、モックや設定値で切り替えられる作りにする
- **現在の仕様は3人プレイ前提**。「3人以上に対応するとき見直す」と書いた箇所は §9 に集約している

---

## 0. 確定したゲーム仕様

| 項目 | 決定 |
|---|---|
| 人数 | 3人（開発状況次第で増やす可能性あり） |
| 役割 | ロビーでプレイヤーが選ぶ（人A / 人B / 人C） |
| 遊ぶ場所 | 遠隔に対応 |
| ジェスチャーの見せ方 | 人Bが数秒録画し、人Cが**録画を再生して見る**（ライブ配信なし） |
| 録画 | お題表示 → カウントダウン → 数秒で自動終了 → 自動送信。**エフェクトを含める**（フロント担当） |
| AIに送るもの | **手の座標データのみ**。録画・画像はAIに渡さない |
| エフェクト | フロントの担当に任せる。API契約には含めない |
| 制限時間 | 時間切れ時は「できているところまで」送る。**文章は締切時に端末が自動送信**。自動送信が届くよう、締切後に**短い猶予**（案: 5秒）を設ける。各段の秒数は、全体を作ってから試しながら決める |
| 空の文章 | プロンプト設定に「空の場合のプロンプト」を用意する |
| 情報公開（進行中） | 自分の担当が終わった人にだけ、前の段を見せる |
| 情報公開（終了・失敗後） | 結果発表を兼ね、**ロビーに戻るまで**、全員が全段を見られる |
| ロビーに戻った人 | **履歴は見られない** |
| 録画の削除 | 録画は他の人に見せるためだけに保存する。**全員がロビーに戻ったときに削除**。保険として、次のゲーム開始時と Storage の自動削除（案: 24時間）でも削除する |
| 録画が届かない | 録画は自動なので通常は発生しない。**録画の保存が完了するまで、人Cの段へ進めない**。端末が生きているのに届かない（通信失敗）場合は、端末が再試行したうえで、**進行不可で中断**する |
| 途中離脱 | 誰かが途中で落ちたら**ゲームを中断**する（3人以上に対応するときに見直す）。離脱は定期的な生存確認（ハートビート）の途絶で判定し、**通信失敗とは区別**する |
| AI失敗（メイン） | 裏で3回リトライ → 失敗なら表示を出して**進行不可**。ロビーに戻るまで履歴は全員が見られる |
| 裏のAI読み取りだけ失敗 | 3回リトライ後に**失敗表示を出すだけ**。他の進行は止めない |
| ゲームの長さ | 1回ごとにロビーへ戻る。戻るのは**各プレイヤーのタイミング** |
| 同意 | ゲーム開始時（名前設定時）にカメラ・座標送信・録画保存について同意を取る |
| 類似度 | 開発次第（PoC後に見せ方を決める） |

---

## 1. 共通ルール

| 項目 | 取り決め |
|---|---|
| 項目名 | `snake_case`（APIとFirestoreのみ。TS内の変数は camelCase のままでよい） |
| ID | Firestore の自動ID（文字列） |
| 時刻 | ISO 8601 UTC（例: `2026-11-08T05:00:00Z`）。Firestore内は Timestamp 型 |
| 認証 | Firebase 匿名ログインの ID トークンを `Authorization: Bearer <token>` で送る |
| URL | `/api/...` に名詞で揃える |
| 入力検証 | バックエンドは Pydantic。長さ・サイズに上限を設ける |
| 受理後に処理する操作 | HTTP **202** を返し、結果は Firestore で全員に届ける |
| 重複防止 | 書き込み系リクエストに `request_id`（端末で生成するUUID）を付ける |
| 内部呼び出し | Cloud Tasks → Worker はサービスアカウント認証。`/internal/...` は外部公開しない |

### エラー形式（全API共通）

```json
{ "error": { "code": "NOT_YOUR_TURN", "message": "あなたの番ではありません" } }
```

`code` はプログラムが判断する文字列、`message` は画面にそのまま出せる日本語。

| HTTP | 意味 | コード例 |
|---|---|---|
| 400 | 入力ミス | `INVALID_INPUT`, `TEXT_TOO_LONG`, `PAYLOAD_TOO_LARGE`, `UNSUPPORTED_MEDIA_TYPE` |
| 401 | 未ログイン・期限切れ | `UNAUTHENTICATED` |
| 403 | 権限なし | `NOT_YOUR_TURN`, `NOT_HOST`, `CONSENT_REQUIRED`, `HISTORY_LOCKED` |
| 404 | 存在しない | `ROOM_NOT_FOUND`, `ASSET_NOT_FOUND` |
| 409 | 状態の食い違い・重複 | `ALREADY_SUBMITTED`, `DEADLINE_PASSED`, `ROLE_TAKEN`, `ROOM_FULL`, `ROLES_NOT_READY`, `INVALID_STATE` |
| 429 | 試行回数超過 | `TOO_MANY_ATTEMPTS`（参加コードの総当たり対策） |
| 500 | サーバー側の失敗 | `AI_FAILED`, `INTERNAL` |

---

## 2. 同意（カメラ・座標・録画）

名前設定時に、次の内容への同意をチェックボックスで取る。

1. カメラを使うこと
2. 手の座標がAIに送られること（映像・画像はAIに送らない）
3. 録画が保存され、**同じ部屋のプレイヤーに見られる**こと
4. 録画は**全員がロビーに戻った時点で削除される**こと（保険として、一定時間後にも自動削除される）

- 同意の記録は `players/{uid}.consented_at`（サーバーが書く）
- 同意がないプレイヤーは、部屋の作成・参加・ジェスチャー系APIを使えない（`CONSENT_REQUIRED`）

---

## 3. API 一覧

| # | メソッド / URL | 内容 | 権限 | 応答 |
|---|---|---|---|---|
| 1 | `POST /api/rooms` | 部屋を作る | ログイン済み | 200 |
| 2 | `POST /api/rooms/join` | 参加コードで入室 | ログイン済み | 200 |
| 3 | `POST /api/rooms/{room_id}/role` | 役割を選ぶ・変更する | 参加者 | 200 |
| 4 | `POST /api/rooms/{room_id}/start` | ゲーム開始 | ホストのみ | 202 |
| 5 | `GET /api/rounds/{round_id}/my-input` | 自分の担当の入力素材 | 現在の担当者 | 200 |
| 6 | `POST /api/rounds/{round_id}/steps/{step_index}/submit` | 文章の提出 | 現在の担当者 | 202 |
| 7 | `POST /api/rounds/{round_id}/gesture/start` | ジェスチャー開始 | 人B | 200 |
| 8 | `POST /api/rounds/{round_id}/gesture/batches` | 座標バッチ送信 | 人B | 202 |
| 9 | `POST /api/rounds/{round_id}/gesture/video` | 録画アップロード（保存完了後に返す） | 人B | 200 |
| 10 | `POST /api/rounds/{round_id}/gesture/finish` | ジェスチャー終了 | 人B | 202 |
| 11 | `GET /api/rounds/{round_id}/history` | 履歴（見せてよい段のみ） | 参加者（§6の条件） | 200 |
| 12 | `GET /api/rounds/{round_id}/assets/{asset_id}` | 画像・録画の取得 | 参加者（§6 の「現在の入力素材」か「公開済み履歴」のどちらか） | 200 |
| 13 | `POST /api/rooms/{room_id}/leave` | ロビーへ戻る（自分だけ）。**部屋が `waiting`（ロビー）のときは、部屋から外れる**（ホストなら次の人に交代） | 参加者 | 200 |
| 14 | `POST /api/rooms/{room_id}/heartbeat` | 生存確認（離脱の判定用） | 参加者 | 200 |

手動再試行（`/retry`）は無い。AI失敗は自動リトライのみで、失敗確定後は進行不可。

### 入力素材の取得（API #5）

`GET /api/rounds/{round_id}/my-input` は、現在の担当者に入力素材と締切を返す。
人BのジェスチャーSTEPでは、次の2項目を追加で返す（2026-11-08、後方互換な追加として承認）。

```json
{
  "step_index": 2,
  "type": "gesture",
  "deadline_at": "2026-11-08T08:00:08Z",
  "input": {"kind": "text", "text": "犬が走る"},
  "countdown_seconds": 15,
  "record_seconds": 8
}
```

- 秒数は**ゲーム開始時に固定した設定スナップショット**から返す。
  開始後に `config/game` が変わっても進行中ラウンドには反映しない。上の秒数は共通既定15秒・8秒を使用した例であり、保存済みの明示設定によって異なる。
- 共通既定は準備15秒・録画8秒。既存の `config/game` に値がある場合はそちらを優先し、進行中ラウンドは開始時snapshotを維持する。実Firestoreの `config/game` への反映は、別途承認を得て行う作業であり、このコード変更では書き換えない。Cloudでは設定ドキュメント自体が未作成の場合、従来どおりゲーム開始を拒否する。
- `countdown_seconds` / `record_seconds` はジェスチャーSTEPでのみ返す。人A・人Cの応答は変更しない。
- `deadline_at` は既に確定した締切。再取得や `gesture/start` によって延長しない。共通既定ではSTEP有効化から23秒（準備15秒＋録画8秒）、受付猶予5秒を加えた28秒時点が締切処理の実行可能時刻となる。
- 担当者以外は `NOT_YOUR_TURN`（403）。設定全体をクライアントへ公開する変更ではない。

### 3-1. 部屋を作る / 入る（同意つき）

```
POST /api/rooms
{ "name": "けいご", "consented": true, "request_id": "..." }

200
{ "room_id": "abc", "join_code": "4821", "player_id": "<uid>" }
```

```
POST /api/rooms/join
{ "join_code": "4821", "name": "みく", "consented": true, "request_id": "..." }

200
{ "room_id": "abc", "player_id": "<uid>" }
```

エラー: `ROOM_NOT_FOUND`, `ROOM_FULL`, `CONSENT_REQUIRED`, `TOO_MANY_ATTEMPTS`

### 3-2. 役割を選ぶ

```
POST /api/rooms/{room_id}/role
{ "role": "A", "request_id": "..." }     // "A" | "B" | "C"

200
{ "accepted": true }
```

- 他の人が選択済みなら `ROLE_TAKEN`（409）。Transaction で確定する
- 自分が選び直すのは可（開始前のみ）。`role: null` で解除
- 開始後は `INVALID_STATE`

### 3-3. ゲーム開始

```
POST /api/rooms/{room_id}/start
{ "request_id": "..." }

202
{ "accepted": true, "round_id": "r_1" }
```

- ホスト以外は `NOT_HOST`
- 全役割が埋まっていないと `ROLES_NOT_READY`
- 開始時に、人数からSTEPリストを生成する（§4）。3人なら6段
- 開始時に、前ラウンドの録画が残っていれば削除する（§7-4 の保険）

### 3-4. 文章の提出

```
POST /api/rounds/r_1/steps/1/submit
{ "text": "赤い屋根の家の前で犬が寝ている", "request_id": "6f1c...", "is_auto": false }

202
{ "accepted": true }
```

- `is_auto`: 締切で端末が自動送信したとき `true`（サーバーは記録するだけ）
- 空文字・空白のみも受け付ける。AIへ渡すときは「空の場合のプロンプト」を使う（§7-2）
- 担当外は `NOT_YOUR_TURN`、二重送信は同じ `request_id` に同じ結果を返す、提出済みは `ALREADY_SUBMITTED`
- **受付期限は `deadline_at` + 猶予**（案: 5秒）。端末は締切ちょうどに自動送信するため、通信の遅れで `deadline_at` を少し過ぎても受け付ける。受付期限を過ぎたら `DEADLINE_PASSED`
- 端末は、送信に失敗したら、同じ `request_id` で数回再送する（受付期限まで）

### 3-5. ジェスチャー（座標）

座標データの中身は F4 / B5 の担当が決める。**共有するのは入口と出口だけ。**

```
POST /api/rounds/r_1/gesture/start
{ "request_id": "..." }
200 { "gesture_session_id": "g_1", "deadline_at": "..." }
```

```
POST /api/rounds/r_1/gesture/batches
{
  "gesture_session_id": "g_1",
  "sequence_number": 0,
  "mirrored": false,
  "samples": [
    { "timestamp_ms": 0,
      "hands": [ { "handedness": "Right",
                   "landmarks": [ {"x":0.42,"y":0.31,"z":-0.02} ] } ] }
  ]
}
202 { "accepted": true }
```

- `landmarks` は例のため省略。実際は検出した手ごとに21点
- 連番（`sequence_number`）の重複は無視し、欠番は許容する（時間切れで途中までの場合があるため）
- バッチの最大サイズと送信間隔は PoC で決める
- エフェクトに関する項目は**契約に含めない**（フロントの描画のみ）

```
POST /api/rounds/r_1/gesture/finish
{ "gesture_session_id": "g_1", "request_id": "..." }
202 { "accepted": true }
```

- `finish` を受けると、裏のAI読み取りジョブを登録する（§7-3）

### 3-6. 録画のアップロード

```
POST /api/rounds/r_1/gesture/video
Content-Type: multipart/form-data
  gesture_session_id=g_1
  request_id=...
  file=<webm/mp4 数秒>

200 { "accepted": true, "asset_id": "a_7" }
```

- **Storage への保存と `assets` の記録が終わってから 200 を返す**（数秒のクリップなので同期で足りる）。人Cの段へ進むのは、この保存が完了してから（§5）
- 数秒のクリップを前提に、**サイズ上限**（案: 10MB）と長さ上限を設ける。超過は `PAYLOAD_TOO_LARGE`
- 形式は許可リスト（案: `video/webm` → `.webm`、`video/mp4` → `.mp4`）。それ以外は `UNSUPPORTED_MEDIA_TYPE`。サーバーはヘッダーだけでなく、**ファイルの先頭バイトでも形式を確認**する
- 保存先: `rooms/{room_id}/rounds/{round_id}/videos/{asset_id}.{ext}`（非公開 Storage）。**拡張子と MIME タイプは実際の形式に合わせて保存**し、`assets` の `content_type` に記録する。取得時は、その `content_type` で返す
- **録画はAIの処理に流さない**。Worker は録画ファイルに触れない
- 端末は、アップロードが失敗したときに数回再試行する（回数は未決定。案: 3回）

### 3-7. 履歴

```
GET /api/rounds/r_1/history
200
{
  "round_status": "playing",
  "visible_until_step_index": 2,
  "steps": [
    { "step_index": 0, "type": "image_gen", "actor": "ai", "status": "done", "image_asset_id": "a_1" },
    { "step_index": 1, "type": "text", "actor": "player", "player_id": "<uid>", "role": "A", "status": "done", "text": "..." }
  ],
  "result": null
}
```

見せる範囲は §6 のルールに従う。見せてはいけない段は `steps` に含めない。ロビーに戻った人には `HISTORY_LOCKED`（403）を返す。

### 3-8. 画像・録画の取得

担当中の人は、自分の入力素材（人A: 最初の画像、人C: 人Bの録画）を、担当が終わる前に取得する必要がある。そのため、`my-input` が素材の `asset_id` を返す。

```
GET /api/rounds/r_1/my-input
200
{ "step_index": 1, "type": "text", "deadline_at": "...",
  "input": { "kind": "image", "asset_id": "a_1" } }
```

`GET /api/rounds/{round_id}/assets/{asset_id}` は、次の**どちらか**を満たすときだけ、`assets` の `content_type` で返す（§6）。

1. **現在の入力素材**: 自分のSTEPが `active` で、その素材が自分の `my-input` の素材である
2. **公開済み履歴**: §6 の履歴の条件を満たす

どちらも満たさなければ `HISTORY_LOCKED`（403）。録画が削除済みなら `ASSET_NOT_FOUND`（404）。
生成画像も24時間のStorage自動削除で実体がなくなった場合は同じ404を返す。履歴・最終結果の記録は維持する。

### 3-9. ロビーへ戻る

```
POST /api/rooms/{room_id}/leave
{ "request_id": "..." }
200 { "accepted": true }
```

- 自分だけがロビーへ戻る。他のプレイヤーは、戻るまで履歴を見続けられる
- **戻った人は、そのラウンドの履歴を見られない**（§6）
- 全員が戻ったら、部屋を `waiting` に戻し、録画を削除する（§7-4）

### 3-10. 生存確認（ハートビート）

```
POST /api/rooms/{room_id}/heartbeat
200 { "accepted": true }
```

- 端末が定期的に送る（案: 5秒おき）。サーバーは `players/{uid}.last_seen_at` を更新する
- 「ゲーム中のプレイヤーが生きているか」を知る唯一の手がかり。**通信失敗と離脱を区別する**ために使う（§7-1）

---

## 4. Firestore の構造

**書き込みはサーバーのみ。スマホは読むだけ。**

```
rooms/{room_id}
 ├ status: waiting | playing | finished | failed
 ├ fail_reason: ai_failed | communication_failed | player_dropped | null
 ├ join_code, host_player_id, created_at
 ├ players/{uid}
 │    ├ name, role (A|B|C|null), consented_at, last_seen_at
 │    └ phase: lobby | playing | viewing | returned
 └ rounds/{round_id}                       ← 全員が読める（公開状態）
      ├ status, current_step_index, revision
      ├ gesture_ai_status: pending | processing | done | failed
      ├ result_status: pending | processing | ready | failed
      ├ steps/{step_index}
      │    ├ type, actor (player|ai), player_id, status
      │    ├ started_at, deadline_at, timed_out
      │    └ （中身の text や asset_id は置かない ← 履歴APIで返す）
      ├ private/main                       ← サーバーだけが読める
      │    └ odai_text, 各段の text / asset_id / ai_conclusion など
      ├ assets/{asset_id}                  ← サーバーのみ（種別・パス・MIMEタイプ・作ったSTEP・作成時刻）
      ├ jobs/{job_id}                      ← サーバーのみ
      │    └ kind, status, attempt, last_error, revision
      └ result/final                       ← 終了後のみ生成（サーバーが書く）
join_codes/{join_code}                     ← サーバー側で照合
```

- **公開側に置くのは進行状態だけ**。お題・途中の文章・画像パス・AIの読み取り結果は `private/main` に置き、履歴APIで返す
- 画像・録画の本体は Cloud Storage。Firestore には `asset_id` のみ
- STEP の例（3人）:

| step_index | type | actor | 担当 |
|---|---|---|---|
| 0 | image_gen | ai | お題から画像生成 |
| 1 | text | player | 人A: 画像を見て文章化 |
| 2 | gesture | player | 人B: 文章を見てジェスチャー（録画） |
| 3 | text | player | 人C: 録画を見て文章化 |
| 4 | image_gen | ai | 人Cの文章から最終画像 |
| 5 | conclude | ai | 最終画像から、お題と同じ形式の短文（「〜している〇〇」）で推測 |

- 裏のAI読み取り（座標→文章）は STEP 2 と並行して動く。メインSTEPとは別に `gesture_ai_status` と `jobs` で管理する（STEPを勝手に飛ばさない）
- STEPを `type` と `actor` で持つので、人数を増やしても STEPリストの生成ロジックだけ変えれば済む

---

## 5. 状態遷移（誰が変えるか: サーバーのみ）

| 対象 | 状態の流れ |
|---|---|
| ROOM | `waiting → playing → finished` / `playing → failed`。全員がロビーに戻ったら `waiting` へ |
| 人のSTEP | `waiting → active → done` / `timeout` |
| AIのSTEP | `pending → processing → done` / `failed` |
| 裏の読み取り（gesture_ai_status） | `pending → processing → done` / `failed`（failed でも他は止めない） |
| RESULT | `pending → processing → ready` / `failed` |
| プレイヤー（phase） | `lobby → playing → viewing → returned`（戻る操作でlobbyへ） |

`failed` になる理由は `fail_reason` に入れる（`ai_failed`、`communication_failed`、`player_dropped`）。

### 進行の条件（録画のSTEP）

人Bのジェスチャー STEP（`step_index = 2`）を `done` にして人Cの STEP を `active` にするのは、次の**両方**がそろったときだけ。

1. 録画の保存が完了している（`gesture/video` が 200 を返し、`assets` に記録されている）
2. ジェスチャーの終了を受け取っている（`gesture/finish`、または受付期限の到達）

録画の保存前に人Cへ進めない。座標と `finish` だけが先に届いても、録画の完了を待つ。

### 更新の安全装置

| 仕組み | 防ぐもの |
|---|---|
| `request_id` | 連打・再送。同一IDには同じ受付結果を返す |
| Transaction | 「STEPが active・担当者が一致・未提出」を同時に確認して1回だけ確定 |
| `revision` | 古いAI結果で最新状態を上書きすること |
| `job_id` | Cloud Tasks の再配送による二重確定（ジョブは冪等に作る） |

---

## 6. 履歴の公開ルール（サーバーで判定）

| 状況 | 見られる範囲 |
|---|---|
| ゲーム進行中 | **自分の担当が `done` になった人だけ**、前の段まで（自分の段以前） |
| 自分の担当がまだの人 | 何も見えない（自分の `my-input` のみ） |
| `finished` / `failed`（ロビーに戻る前） | **全員が全段**（画像・録画・文章・AIの読み取り・結果） |
| ロビーに戻った人 | **見られない**（`HISTORY_LOCKED`） |

- 画面で隠すだけでは不可。**履歴APIとassets APIが、同じ関数で判定**する

### 素材（画像・録画）を取得できる2つの条件

履歴の条件だけでは、担当中の人が自分の入力素材（人Aの画像、人Cの録画）を取得できない。そのため、`assets` の権限は次の**2つのどちらか**にする。

| 条件 | 対象 | 判定 |
|---|---|---|
| **現在の入力素材** | 自分のSTEPが `active` の人 | その素材が自分の `my-input` の素材と一致する |
| **公開済み履歴** | 上の履歴の表で見せてよい段 | §6 の履歴の条件を満たす（ロビーに戻った人は不可） |

- 人Aは担当中に最初の画像を、人Cは担当中に人Bの録画を見られる。人Aが人Bの録画を見られるのは、自分の担当が終わったあと
- 現在の入力素材は、そのSTEPが `active` の間だけ。担当が終わったあとは、履歴の条件で判定する

---

## 7. 時間切れ・AI処理・失敗・削除

### 7-1. 時間切れと離脱

- 各STEPの `deadline_at` はサーバーが決めて書き込む。端末はカウントダウン表示だけ
- **受付期限**: `deadline_at` + 猶予（案: 5秒）。端末は `deadline_at` ちょうどに自動送信し、通信の遅れで少し過ぎても、受付期限までは受け付ける
- **文章**: 締切時に端末が `submit`（`is_auto: true`）を自動送信。入力中の文章を、できているところまで送る
- **録画**: カウントダウン後、数秒で自動終了し、`gesture/video` と `gesture/finish` を自動送信
- **座標**: バッチで送られているぶんをそのまま使う（途中までで可）
- **端末の再送**: 送信に失敗したら、同じ `request_id` で数回再送する（受付期限まで）
- **サーバーの保険**: Cloud Tasks の遅延タスクを、受付期限に発行する。そのとき STEP がまだ `active` のままなら、**生存確認（§3-10）で、次の2つに分ける**

| 判定 | 条件 | 動作 |
|---|---|---|
| **離脱** | 担当者の `last_seen_at` が一定時間（案: 15秒）以上途絶えている | ゲームを中断（`failed` / `player_dropped`） |
| **通信失敗** | `last_seen_at` は新しいのに、提出・録画が届いていない | ゲームを中断（`failed` / `communication_failed`） |

- どちらも中断だが、**理由を分けて記録**する。画面の表示も分けられる（例: 「〇〇さんが退出しました」／「通信がうまくいきませんでした」）
- 端末が接続中で、送信も届いていれば、空の文章で進むのは「接続したまま何も書かなかった」ときだけ
- 通信失敗のとき、文章は「空で進める」案もある（§8）
- 各段の秒数は**設定値**にして、全体を作ってから試しながら決める

### 7-2. AI処理（Cloud Tasks → Worker）

- API は受理して 202 を返し、ジョブを `jobs/{job_id}` に登録して Cloud Tasks に投げる
- Worker だけが AI キー（Secret Manager）で Gemini を呼ぶ
- Gemini に送るのは**座標データのみ**（画像生成は文章を、結論は最終画像をモデルに渡す。ジェスチャーの録画・映像は渡さない）
- **空の文章**: 文章が空（空白のみを含む）のときは、プロンプト設定の「空の場合のプロンプト」を使って画像を生成する
- モデルIDは設定値（利用可否・料金・クォータは PoC で確認してから固定）

### 7-3. 失敗とリトライ

| 異常 | 対応 |
|---|---|
| 通信失敗・レート制限 | 間隔を広げて再試行（合計**3回**） |
| 不正なAI出力形式 | 検証して再試行（上限は上と共通） |
| 不正なAPI入力 | 再試行しない（400系） |
| メインのAI処理が3回失敗 | ジョブを `failed` に確定 → ROOM を `failed`（`ai_failed`）、進行不可 |
| 裏の読み取りだけ3回失敗 | `gesture_ai_status` を `failed` にして、画面に失敗表示を出す。**他の進行は止めない** |

- 失敗確定後も、ロビーに戻るまでは**全員が履歴を見られる**（§6）。各プレイヤーは自分のタイミングで `leave` できる
- 画面は `failed` の表示を出す（例: 「AIがうまく動きませんでした」）

### 7-4. 録画が届かない場合と、録画の削除

**録画が届かない**
- 録画は自動で撮るため、通常は必ず届く。届かないのは通信の問題のときだけ
- 端末はアップロードを数回再試行する。それでも保存が完了せず、受付期限を過ぎたら、§7-1 の判定で中断する（端末が生きていれば `communication_failed`、途絶していれば `player_dropped`）
- **録画の保存が完了するまで、人Cの段へ進まない**（§5）

**録画の削除（3段構え）**
1. **全員がロビーに戻ったとき**: 録画と `assets` の記録を削除する（基本）
2. **次のゲーム開始時**: 前ラウンドの録画が残っていれば削除する（保険）
3. **Storage の自動削除**: 作成から一定時間後（案: 24時間）に削除する（保険。放置された部屋の対策）

- 画像（生成画像）の保存期間は、この仕様では決めていない（§8）

---

## 8. 未決定事項（決めるまではモック・設定値で切り替え可能にする）

| 優先 | 項目 | 案 |
|---|---|---|
| P0 | 各段の秒数（文章入力・カウントダウン・録画の長さ） | 設定値にして、全体を作ってから試しながら決める |
| P0 | 部屋が `waiting` に戻る条件 | 全員が `leave` したとき（ホストの開始操作での強制リセットは未決定） |
| P0 | ハートビートの間隔と、離脱とみなす時間 | 案: 5秒おき／15秒途絶で離脱 |
| P1 | 通信失敗のとき、文章の段を中断せず「空で進める」か | 案: 中断（録画の段と揃える）。空で進める案もある |
| P1 | 端末の再送回数（文章・録画） | 案: 3回 |
| P1 | AIが安全フィルタで拒否したときの扱い | 再試行せず失敗として扱う（案）。代わりのプロンプトに切り替える案もある |
| P1 | 録画の形式（iPhone は mp4、Android は webm のことがある） | 許可リストを `webm`・`mp4` にして、再生の互換をPoCで確認 |
| P1 | 自動リトライの間隔・タイムアウト秒数 | PoC後に決める |
| 決定済み | 生成画像の保存期間 | 作成から24時間（録画と同じ。Storage の自動削除に任せる）。2026-11-08 決定 |
| P2 | 類似度の見せ方（点数換算） | PoCの分布を見て決める |
| P2 | アプリ名・UI・演出 | 後回し |

---

## 9. 3人以上に対応するときに見直す項目

| 項目 | 今の仕様（3人） | 見直す内容 |
|---|---|---|
| 途中離脱 | ゲームを中断する | 離脱した人を飛ばして続けられるか |
| ロビーに戻った人の履歴 | 見られない | 戻ったあとも見られるようにするか |
| 役割 | A / B / C を1人ずつ | 同じ役割が複数人になるか、役割を増やすか |
| ゲームの長さ | 1回ごとにロビーへ戻る | 待ち時間が長くならない流れ |

---

## 10. 決定ログ（会議で記入）

| # | 項目 | 決めたこと・理由 | 担当 | 期限 |
|---|---|---|---|---|
| 1 | 共通ルール | | | |
| 2 | エラーの形 | | | |
| 3 | 各APIの入出力 | | | |
| 4 | Firestore（項目名・書く人） | | | |
| 5 | 状態の値 | | | |
| 6 | ジェスチャーの出入り口 | | | |
| 7 | 録画の受け渡しと削除 | | | |
| 8 | 履歴の公開ルール | | | |
