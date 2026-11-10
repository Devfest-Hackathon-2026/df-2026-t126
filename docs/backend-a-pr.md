# PRタイトル案

feat: バックエンドAのAPI・認可とB Workerの永続接続・復旧を追加

# PR本文案

実装のなかったバックエンドAに14 APIとFirebase認証・Firestore/Storageアダプターを追加します。
3人の提出・録画・STEP進行をTransactionで管理し、再送や同時提出でも1回だけ確定します。
履歴は担当完了後に自分の段以前のみ、終了/失敗後は帰還するまで全段を公開します。
録画保存完了とfinishがそろうまでCへ進まず、通信失敗・離脱・削除失敗も扱います。

Cloud Tasks配送は永続outbox経由。内部期限処理は公開APIから分離しています。
通常起動はオフラインで、実Cloud接続は明示的なopt-inが必要です。
DockerfileとRun/Hosting設定はレビュー用の未適用案です。

main 82bf14eを作業ブランチへ統合し、B Worker/dataを無変更で取り込み、B実handle_job/run_jobにIO/Sinkを注入します。
結果保存後の進行失敗はAIを再呼出せず復旧し、キュー再配送が尽きた場合も進行/実行outboxから再開・失敗確定します。
未採用アセットの閲覧を拒否し、FirestoreのABORTED競合はスナップショットを取り直して限定再試行します。

人Bのmy-inputには開始時configのcountdown_seconds/record_secondsを追加。
開発用api.localで、実B Worker+モックAIとメモリ配送によるチーム結合が可能です。
実Cloud用の起動入口は変更せず、local/emulator以外は拒否します。

## 検証

- オフラインpytest：118 passed、Emulator専用3件skip。
- Emulator Suite：Rules 5 passed、Python 121 passed。
- Firestore Transactionの競合、Auth匿名ログイン、Storage SDK保存/取得/削除をローカルで検証。
- ruff check/format、compileall、pip check、shell構文、git diff --check成功。
- 12同時提出×5回、古いrevision、重複配送、保存後のWorker停止、最終試行の停止と非致命的失敗を検証。
- wheel build/別ディレクトリinstallと、ソース外からWorker/お題データ/内部アプリをimport検証。

## レビュー時の確認

- BのAI/お題/Workerとフロント内部は変更していません。
- 最新正本はBのwrite_job_result→Aのadvance_step。JobPayload/JobResult等はBのスキーマと一致。
- Bの元のworker.mainのLogSinkは維持。永続Worker入口はSERVICE_ROLE=worker→api.worker:appの統合案。
  設定/Storageの競合はローカルで解消し、担当者への確認はdocs/integration-handoff.mdに集約。
- 実uvicorn+匿名Auth/Firestore/Storage Emulatorによる3人HTTP一巡も成功。
- A/Bの実応答・公開文書25例とフロントのTS型を照合。フロント内部はmain版で、実Backend接続は未実装。
- 実クラウド・IAM・デプロイ・実機ブラウザ互換・Docker buildは未検証です。
- フロントbuild/lintは同梱Nodeの署名制約で実行不可。tsc -bは成功。
- 実装/制約/再開手順はdocs/backend-a-progress.md、接続境界はdocs/backend-a-integration.md参照。

このファイルは本文案です。ユーザーの新しい許可に基づきAブランチだけ通常Pushしました。
main起点の一時ローカルブランチでも競合0件・Emulator121件/Rules5件成功。
PR作成・実際のmain変更は行っていません。詳細はbackend-a-merge-validation.md。


## 最新main更新（PR #2）

main 82bf14eの生成画像24時間保存とPNG実測報告を反映。changelogの競合はA/B両方の決定を保持して解消。
実体消失後は画像404・履歴metadata維持を新規テスト。Bの結合了承はユーザーから受領済み。
実バケット/PNG確認はBの報告であり、Aによる実環境再検証ではない。
残る運用値はqueue/専用配送SA/deadline実URLと各サービスのOIDC。画像保持・PNG自体は未決定事項から外す。
