# 開発環境のメモ（Mac で、テストや実行が極端に遅いとき）

- 作成: 2026-11-08（B）

## 症状
テストが10分以上かかる、`python` の起動や読み込みが止まって見える、Google の認証が応答しないように見える。

## 原因（B の環境で確認）
リポジトリが `~/Documents`（iCloud Drive の同期対象）にあり、Mac のディスクが 95% 埋まっているため、macOS が**ファイルの実体を iCloud に追い出す**（`ls -lO` で `dataless` と表示される）。Python は、起動のたびに数千ファイルを読むので、**1つずつ iCloud から取り戻す**待ちが発生する。`fileproviderd`（iCloud の同期担当）が常に CPU を使う。

実測: 同じテスト（27件）が **190秒 → 0.5秒**（Python の環境を iCloud の外に置いて、一度読み込んだあと）。

## 対策
1. **Python の環境（`.venv`）を iCloud の外に置く**（効果が最も大きい）:
   ```bash
   export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/gesture-relay-game"   # ~/.zshrc に書いておく
   uv sync --python 3.12 --group dev
   uv run pytest -q
   ```
   リポジトリ内の `.venv` は、使わなくなるので、削除してよい（`.gitignore` 済み）。
2. **ソースのフォルダを「ダウンロードを保持」にする**（Finder でフォルダを右クリック → 「ダウンロードを保持」）。追い出されなくなる。
3. **ディスクの空きを増やす**（Data ボリュームが 95%）。空きが少ないと、macOS は、追い出しを続ける。
4. **根本策**: リポジトリを iCloud の外（例: `~/Developer/gesture-relay-game`）に移す。GitHub Desktop で、リポジトリを追加し直す必要がある。
5. メモリが足りないとき（スワップが 4GB 近い）は、ブラウザのタブや、使っていないアプリを閉じる。
