# フロント

React + TypeScript + Vite。仕様は [docs/specification.md](../docs/specification.md) を参照。

```bash
npm install
npm run dev
```

## 本物のサーバーで動かす

A の `docs/team-integration-guide.md` の手順で、エミュレーターと A の API を起動してから実行する。

```bash
npm run dev:emulator
```

`http://localhost:5173/?dev=3` で3人分を並べて遊べる。

## モックで動かす

`npm run dev` はブラウザ内の偽物のサーバー（モック）で動く。本物の API は不要。

| URL | 内容 |
|---|---|
| `http://localhost:5173/?dev=3` | 3人分の画面を横に並べて、1台で遊ぶ |
| `http://localhost:5173/?dev=3&text_seconds=6` | 文章の制限時間を6秒にして、締切の自動送信を試す |
| `http://localhost:5173/?dev=3&gesture_read_ms=30000` | 裏の読み取りを30秒かかる設定にして、遅いときの動きを試す |

画面の下の「開発用」から、失敗の表示を試せる。「全部消す」で最初からやり直せる。

## カメラと録画を確かめる

| URL | 内容 |
|---|---|
| `http://localhost:5173/?poc` | ゲームを通さずに、カメラ、手の検出、軌跡、録画を確かめる |
| `http://localhost:5173/?poc&video_mode=skeleton` | 映像を映さず、手の骨格だけを録画する |
| `http://localhost:5173/?dev=3&fake_camera=1` | カメラを使わず、仮の入力でゲームを通す |

iPhone のカメラは HTTPS でないと動かない。`npm run dev:https` で起動し、同じ Wi-Fi の iPhone で `https://<MacのIPアドレス>:5173/?poc` を開く。証明書の警告が出たら、詳細から進む。

## テスト

```bash
npm test
```

ネットにつながらない環境でビルドするときは、手の検出モデルのダウンロードを飛ばせる。そのビルドでは手の検出が動かない。

```bash
SKIP_MEDIAPIPE=1 npm run build
```

## Firebase Hosting に置く

最初の1回だけログインする。

```bash
node_modules/.bin/firebase login
```

公開する。ビルドは自動で行われる。

```bash
node_modules/.bin/firebase deploy --only hosting
```

## ファイルの役割

| 場所 | 役割 |
|---|---|
| `src/api/types.ts` | API と Firestore の型。項目名は仕様書と同じ snake_case |
| `src/api/backend.ts` | 画面が使う窓口。モックと本物はこの形で差し替える |
| `src/api/mock/` | モック。`backend_a/game.py` と同じルールで動く |
| `src/api/real/realBackend.ts` | 本物の窓口。A の API と Firestore を使う |
| `src/game/useGame.ts` | サーバーの状態の購読と、どの画面を出すかの判定 |
| `src/screens/` | 画面 |
| `src/gesture/capture.ts` | ジェスチャーの入力元の窓口と、事前の準備 |
| `src/gesture/camera.ts` | カメラと MediaPipe の手の検出 |
| `src/gesture/effects.ts` | エフェクト。種類を増やすときはここに足す |
| `src/gesture/recorder.ts` | キャンバスの録画 |
| `src/dev/GesturePoc.tsx` | 実機確認のページ |
| `scripts/prepare-mediapipe.mjs` | MediaPipe のファイルを `public/mediapipe` に用意する（Git には入れない） |
