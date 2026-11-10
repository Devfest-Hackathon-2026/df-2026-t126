# システム構成図（2枚目）の相違点と変更案

対象: 「伝言ゲーム システム構成図（仕様書 v2.2・2026-11-07 対応）」。提出ドキュメントの「アーキテクチャ図」に使う予定。
確認した日: 2026-11-09（B）。確認の根拠は、コード（`common/settings.py`、`worker/ai/real.py`）、本番の Cloud Run の設定、`docs/`。
**結論: 流れはほぼ合っている。直す点は4つ。特に、Secret Manager は使っていないので、必ず直す（審査の「安全性」に関わる）。**

## 1. 相違点と変更案（必ず直す）
| # | 図の内容 | 実際 | 変更案 |
|---|---|---|---|
| 1 | **Secret Manager（AI のキー）** の箱と、手順7「Worker が Secret Manager から AI のキーを取り出す」 | **使っていない。** AI は Vertex AI を、Google Cloud の認証（鍵なし）で呼ぶ。キーは、コードにも環境変数にも置いていない | 箱と、Worker→Secret Manager の矢印を**削除**。手順7を「Worker が、Google Cloud の認証（鍵なし）で、Vertex AI を呼ぶ」に書き換える |
| 2 | 「Google AI / Vertex AI / Gemini API（**要決定**）」 | **Vertex AI に決定済み**（Gemini API の鍵方式は、採用しなかった） | 見出しを「**Vertex AI（Gemini）**」に。「要決定」を削除 |
| 3 | **Cloud Scheduler と「期限処理」がない** | **ある。** Cloud Scheduler が毎分、期限処理（Cloud Run の3つ目のサービス）を呼び、時間切れ・止まった処理を回復する。Cloud Tasks も、時間切れの見張りを期限処理に届ける | 「Cloud Scheduler」と「Cloud Run: 期限処理」の箱を足す。矢印: Cloud Scheduler→期限処理、Cloud Tasks→期限処理。流れに手順12を足す |
| 4 | 注釈「Worker を API と同じ Cloud Run サービスに置くか、別サービスにするかは**未確定**」 | **別サービスに決定済み**（API・Worker・期限処理の3つ。Worker と期限処理は非公開） | 注釈を**削除**。Worker は、別の Cloud Run の箱のまま |

## 2. 細かい点（直すと、より正確）
| 図の内容 | 実際 | 変更案 |
|---|---|---|
| 手順3: 端末 → API へ直接 | 実際は **Hosting 経由**（Hosting が `/api/**` を API へ転送） | 矢印を「端末→Hosting→API」にするか、手順3に「（Hosting が `/api/**` を API へ転送）」と書く |
| 「Nano Banana（画像の生成）」 | 通称。実際は **Gemini 3.1 Flash Image**（混雑時は 2.5 Flash Image に自動で切り替え） | 「Gemini Image（画像の生成）」と書く |
| 「Gemini（座標の読み取り・結論）」 | 実際は **Gemini 3.5 Flash** | そのまま。モデル名を書くなら 3.5 Flash |
| 「仕様書 v2.2（2026-11-07）に対応」 | 古い | 「本番の構成（2026-11-09）」に直す |
| 「担当 A」「担当 B」 | チーム内の分担 | 審査員向けなら、削除 |

## 3. 合っているところ（変えない）
Hosting から画面が届く／匿名ログインで ID トークン／API が Firestore・Storage に保存／Cloud Tasks から Worker へ（失敗は最大3回まで再配送）／Worker が結果を Firestore・Storage に保存／公開状態だけがリアルタイムで届く／手の座標を端末の中（MediaPipe）で取り出す／AI に送るのは文章・画像・手の座標だけ（録画の動画は送らない）。
アイコンは、Google Cloud・Firebase の公式（スライドの推奨 cloud.google.com/icons）なので、そのまま使える。

## 4. 「処理の流れ」の書き直し案（番号は、図のまま。7を書き換え、12を足す）
1. Firebase Hosting から、画面ファイルが各端末に届く
2. 端末が Firebase Authentication で匿名ログインし、ID トークンを受け取る
3. 操作（役割選択・文章・手の座標・録画・生存確認）を、ID トークン付きで API に送る（Hosting が `/api/**` を API へ転送）
4. API が担当者・締切を確認し、進行状態を Firestore に書く／録画を Storage に保存
5. AI が必要な処理は、ジョブとして Cloud Tasks に登録（受付は 202 で即返す）
6. Cloud Tasks が Worker にジョブを届ける（失敗時は最大3回まで再配送）
7. **Worker が、Google Cloud の認証（鍵なし）で、Vertex AI を呼ぶ（キーは、どこにも置かない）**
8. Gemini Image・Gemini・Embedding を呼ぶ（AI に送るのは文章・画像・手の座標のみ）
9. AI の結果と生成画像を Firestore／Storage に保存し、次の段へ進める
10. Firestore の公開状態（今どの段か）が、全員の端末にリアルタイムで届く
11. 端末は中身（素材・履歴・画像・録画）を API から受け取る（見てよい人だけ）
12. **Cloud Scheduler が毎分、期限処理を呼び、時間切れや止まった処理を回復する（Cloud Tasks の時間切れの見張りも、期限処理に届く）**

## 5. 確認済みの根拠
- Secret Manager を使っていない: コードに参照なし。Worker の環境変数に、KEY・SECRET を含むものが0件。`common/settings.py` の AI の呼び先は、すべて `vertex`。
- 3つの Cloud Run: `gesture-relay-api`（公開）、`worker`・`gesture-relay-deadlines`（非公開。呼べるのは `tasks-invoker` だけ）。
- Cloud Scheduler: `maintenance-every-minute`（毎分、期限処理の `/internal/maintenance` を呼ぶ）。

## 6. 最新版での修正（2026-11-09 22時ごろ・フロント）
フロントの人間が上の変更案を反映した図（本番の構成・2026-11-09）を作り、コードと照らし合わせて、次を直した。`docs/submission/architecture.png` を差し替え、編集用の元ファイル `docs/submission/architecture.svg` を足した（PNG は SVG から2倍の解像度で書き出したもの。書体はヒラギノで描画）。

| 直したところ | 理由 |
|---|---|
| 期限処理 → データ の矢印を足した（「時間切れ・中断を書く」） | 期限処理は、時間切れの段を締める・中断にする・次の段へ進めるなど、Firestore に書くため |
| ③ の矢印に「※ Hosting の /api/** 転送を通る」と注記 | 図では端末から API へ直接つながって見えたため（説明文とそろえた） |
| ⑦⑧ の説明を「鍵なし認証」「Gemini を呼ぶ」に分けた | 1本の線に番号が2つ並び、分かりにくかったため |
| 処理の流れ ⑫ に「回復して Firestore に書く」を足した | 1つ目と同じ理由 |
| 題名を「ジェスチャー伝言 システム構成図」に | プロダクト名にそろえた |
| 録画を「エフェクト込み・8秒」に | 録画の長さ（`record_seconds` = 8）を具体的に |
