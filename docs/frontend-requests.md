# フロントから A へのお願い

- 作成: 2026-11-08 JST（フロント）
- 見たコード: `origin/codex/backend-a`（コミット `afd375f`）と `origin/main`（コミット `9e4c018`）
- 目標: **11/8 17:00 に、iPhone と MacBook でゲームを通しで動かす**
- 使い方: 終わった項目は「状態」を ✅ に変えてください。仕様を変えたら `docs/changelog.md` にも書きます（書く文章は §4 に用意しました）

この文書は、そのまま AI に渡しても作業できるように、ファイル名と変更内容を具体的に書いています。

---

## 最初に：全体の一覧

A の実装はフロントから見てもよくできていて、API の形はほぼそのまま使えます。ただ、実装を読んだところ、フロントだけでは解決できない点が5つありました。

| # | 困っていること | やること | 作業量 | 状態 |
|---|---|---|---|---|
| 1 | 録画の秒数をフロントが知る方法がない | `my-input` の返す値を2つ増やす | コード数行 | ✅ Aでローカル実装・検証（2026-11-08、ユーザー承認済み）。Aブランチ7061ad4で共有済み、main未反映 |
| 2 | 人Bが文章を読む時間が3秒しかない | Firestore に `config/game` を作る | 画面操作のみ | ⬜ |
| 3 | 録画の送信に使える時間が5秒しかない | 環境変数を1つ変える | 設定のみ | ⬜ |
| 4 | フロントが使う項目が仕様書に載っていない | 仕様書に追記する | 文章の貼り付け | ⬜ |
| 5 | 待っている人のスマホが消灯すると中断する | 環境変数を1つ変える | 設定のみ | ⬜ |

このほかに、§6 に「本物で動かすために必要なもの」をまとめました。**17:00 に間に合わせるには、§6 の 1 と 2 が一番急ぎです。**

フロントは、本物の API がなくても作業できるように、ブラウザの中に偽物のサーバー（モック）を作って進めています。なので、A の作業が終わるまで手が止まることはありません。

---

## 用語

| 言葉 | 意味 |
|---|---|
| 段（STEP） | ゲームの1工程。0〜5 の6段あり、段2が人Bのジェスチャー |
| `deadline_at` | その段の締切の時刻 |
| 猶予（`deadline_grace_s`） | 締切を過ぎても受け付ける秒数。今は5秒 |
| ハートビート | 端末が「生きています」と定期的に送る通信 |

---

## 1. 録画の秒数をフロントに教えてほしい

### 何が起きているか

人Bの段の時間は、次のように決まっています。

```
段が始まる                                    deadline_at
   |------ countdown_seconds ------|-- record_seconds --|-- 猶予 --|
         文章を読む・カウントダウン        録画
```

フロントは「いつ録画を始めて、いつ止めるか」を決める必要があります。そのためには `countdown_seconds` と `record_seconds` の値が要ります。

しかし、今はこの2つをフロントが知る方法がありません。

- `config/game` は `firestore.rules` で読めないようになっている（これは正しい設定です）
- `my-input` も `gesture/start` も秒数を返さない
- Firestore の `started_at` と `deadline_at` からは、2つの**合計**しかわからない

### なぜ困るか

`backend_a/video.py` は、録画が `record_seconds + 0.5秒` より長いと `PAYLOAD_TOO_LARGE` で拒否します。フロントが秒数を知らないと、録画が拒否されて、ゲームが中断する恐れがあります。

### どうしてほしいか

`backend_a/game.py` の `my_input` の最後を、次のように変えてください。

変更前:

```python
            return {
                "step_index": index,
                "type": step["type"],
                "deadline_at": step["deadline_at"],
                "input": input_data,
            }
```

変更後:

```python
            result = {
                "step_index": index,
                "type": step["type"],
                "deadline_at": step["deadline_at"],
                "input": input_data,
            }
            if step["type"] == "gesture":
                result["countdown_seconds"] = private["config"]["countdown_seconds"]
                result["record_seconds"] = private["config"]["record_seconds"]
            return result
```

`private["config"]` を使うのは、ゲーム開始時に保存した値なので、途中で `config/game` を書き換えても影響を受けないからです。

### 確認のしかた

`tests/test_game_api.py` の `test_full_three_player_game_history_and_cleanup` で、人Bの `my-input` を読んでいる箇所の近くに、次を足して `pytest` を実行してください。

```python
    gesture_input = h.get(f"/api/rounds/{rid}/my-input", "b")
    assert gesture_input["countdown_seconds"] == 3
    assert gesture_input["record_seconds"] == 5
```

---

## 2. Firestore に `config/game` を作ってほしい

### 何が起きているか

コードの仮の値は、文章60秒、カウントダウン3秒、録画5秒です。人Bは**カウントダウンの間に文章を読む**ので、読む時間が3秒しかありません。

また、締切は段が始まった瞬間に決まります。`gesture/start` を遅らせても延びません。

さらに、本番（`RUNTIME_MODE=cloud`）では `config/game` が無いとゲームを開始できません。`INVALID_STATE` で拒否されます。

### どうしてほしいか

Firebase コンソールの Firestore で、次のドキュメントを作ってください。コードの変更は不要です。

- コレクション: `config`
- ドキュメント ID: `game`

| フィールド | 型 | 値（仮） |
|---|---|---|
| `text_seconds` | number | 60 |
| `countdown_seconds` | number | 10 |
| `record_seconds` | number | 5 |

値は仮です。仕様書 §8 のとおり、遊んでみてから決めます。`countdown_seconds` の上限は30です。

### 確認のしかた

本番環境で `POST /api/rooms/{room_id}/start` が 202 を返せば成功です。

---

## 3. 猶予を5秒から10秒にしてほしい

### 何が起きているか

録画は締切の直前まで撮ります。そのあと、猶予の5秒の間に、次の全部を終える必要があります。

1. スマホが動画ファイルを完成させる
2. スマホから API へ送る
3. API が動画を検査して Storage に保存する

### なぜ困るか

5秒を超えると `DEADLINE_PASSED` で拒否され、期限の処理でゲームが `communication_failed` になります。会場の Wi-Fi やスマホの回線だと、超える可能性があります。ただし、実際に何秒かかるかは、まだ測っていません。

フロントでも、画質を下げてファイルを小さくします。

### どうしてほしいか

環境変数を `DEADLINE_GRACE_S=10` にしてください。コードの変更は不要です。

**API のサービスと、期限を受けるサービスの両方**に、同じ値を設定してください（`infra/cloud-run-api.yaml.example` と `infra/cloud-run-deadline.yaml.example`）。

### 変えたときの影響

人が本当に落ちたとき、中断の判定が5秒遅くなるだけです。ほかに影響はありません。実機で測って余裕があれば、5秒に戻します。

---

## 4. 仕様書に追記してほしい

### 何が起きているか

A の実装には、仕様書に書かれていない項目があります。実装が間違っているのではなく、**仕様書が追いついていない**状態です。特に `current_round_id` は重要です。ゲーム開始の応答を受け取るのはホストだけなので、ほかの2人はこの項目で `round_id` を知るしかありません。

フロントが使う項目は次のとおりです。

| 場所 | 項目 | 用途 |
|---|---|---|
| `rooms/{room_id}` | `current_round_id` | ホスト以外が `round_id` を知る |
| `steps/{step_index}` | `step_index`、`role`、`is_auto` | 画面の表示 |
| `my-input`（段2） | `input: { kind: "text", text }` | 人Bが読む文章 |
| `my-input`（段3） | `input: { kind: "video", asset_id }` | 人Cが見る録画 |
| `history` の段 | `image_asset_id`、`video_asset_id`、`text`、`gesture_ai_text` | 履歴の表示 |
| `history` の `result` | `odai`、`final_image_asset_id`、`ai_conclusion`、`similarity`、`gesture_ai_text` | 結果の表示 |

### どうしてほしいか

`docs/specification.md` の §3-8 と §4 に上の表の項目を足して、`docs/changelog.md` の一番上に次を貼り付けてください。日時は実際の時刻にしてください。

```markdown
## v2.3 — 2026-11-08 HH:MM JST

実装とフロントの結合のために、仕様書を実装に合わせた。

| 区分 | 内容 | 理由 |
|---|---|---|
| 追加 | `rooms/{room_id}.current_round_id` | ホスト以外が `round_id` を知るため |
| 追加 | `my-input`（段2）の応答に `countdown_seconds`、`record_seconds` | フロントが録画の開始と終了を決めるため。`config/game` はフロントから読めない |
| 追加 | `my-input` の `input` の形（段2は `text`、段3は `video`） | 実装に合わせた |
| 追加 | `steps` の `step_index`、`role`、`is_auto` | 実装に合わせた |
| 変更 | 猶予の案を5秒から10秒に変更 | 録画の完成、送信、検査が5秒で終わらない恐れがあるため |
| 変更 | 離脱とみなす時間の案を15秒から30秒に変更 | 待機中のスマホの消灯で、ゲームが中断しないようにするため |
```

---

## 5. 離脱とみなす時間を15秒から30秒にしてほしい

### 何が起きているか

`deadline()` の見回りは、担当の人だけでなく**3人全員**のハートビートを確認しています。誰か1人でも15秒途絶えると `player_dropped` でゲームが中断します。

### なぜ困るか

人Aや人Cは、ほかの人の番の間、スマホを見ずに待ちます。iPhone の画面が消えたり、別のアプリに移ったりすると、ブラウザの処理が止まり、ハートビートが届かなくなる可能性があります。デモの途中で中断すると大きな失点になります。

フロントでも、画面の消灯を防ぐ機能（Wake Lock）を入れます。ただし、iPhone でどこまで効くかは、まだ確かめていません。

### どうしてほしいか

環境変数を `DROPOUT_AFTER_S=30` にしてください。コードの変更は不要です。§3 と同じく、**API と期限を受けるサービスの両方**に設定してください。

### 変えたときの影響

本当に落ちた人の検出が15秒遅くなります。遊べなくなるわけではありません。

---

## 6. 本物で動かすために必要なもの

上から順に急ぎです。

| # | 必要なもの | 担当 | 状態 |
|---|---|---|---|
| 1 | `codex/backend-a` を `main` に合流する | A・B | ⬜ |
| 2 | API を Cloud Run にデプロイして、URL をフロントに教える | A | ⬜ |
| 3 | Worker の結果を Firestore に書くようにする | B | ⬜ |
| 4 | `firestore.rules` を本番に反映する | A | ⬜ |
| 5 | Firebase の Web 設定値をフロントに渡し、匿名ログインを有効にする | 作成した人 | ⬜ |
| 6 | Hosting の `/api/**` を API へ転送する設定を入れる | A | ⬜ |
| 7 | `CORS_ORIGINS` に `http://localhost:5173` を入れる | A | ⬜ |
| 8 | `gesture_ai_text` の置き場所を決める | A・B | ⬜ |

**1 について。** 試しにマージを計算すると、8ファイルで衝突します。`common/enums.py`、`common/models.py`、`common/settings.py`、`common/storage.py`、`Dockerfile`、`pyproject.toml`、`.gitignore`、`.dockerignore` です。AとBの両方が同じファイルを作ったためなので、2人で話しながら解消してください。

**3 について。** 今の `worker/main.py` は `LogSink` と `MemoryJobIO` を使っていて、結果をログに出すだけです。ここが Firestore に書くようになるまで、段0の画像が完了せず、ゲームが先に進みません。

**4 について。** 反映しないと、フロントが Firestore の状態を読めず、画面が切り替わりません。

**5 について。** Web 設定値とは、Firebase コンソールの「プロジェクトの設定」にある `apiKey` や `projectId` などです。秘密の情報ではなく、ブラウザに置く前提の値です。

**6 について。** フロントのビルド結果は `frontend/dist` に出ます。`infra/hosting.json.example` の `FRONTEND_BUILD_DIRECTORY` はこの値にしてください。Hosting へのデプロイを誰が行うかも教えてください。

**7 について。** 開発中に、手元のフロントから本番の API を呼ぶために必要です。Hosting の転送を使う本番では同じ場所からの通信になるので、影響しません。

**8 について。** A の `history` は `private.gesture_ai_text` を読みますが、`shared-types.md` §3-4 は `result/final.gesture_ai_text` と書いています。また、読み取りの結果を `outputs["2"]` に上書きすると、録画の `asset_id` が消える恐れがあります。フロントは、段2の `gesture_ai_text` と `result.gesture_ai_text` のどちらに入っていても、結果画面の人Cの文章の上に表示します。ただし、置き場所は1つに決めてください。

---

## 7. フロントから渡すもの

iPhone と MacBook で撮った本物の録画ができたら、サンプルを渡します。`backend_a/video.py` の検査に通るかを確かめてください。実機の録画での確認はまだできていません。

---

## 質問があるとき

わからない点があれば、フロント担当に聞いてください。この文書の案は、もっと良い方法があれば変えて大丈夫です。変えたときは、フロントにも教えてください。
