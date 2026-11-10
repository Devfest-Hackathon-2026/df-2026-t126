# main取り込み時の相違点・担当者への確認

> 最新（2026-11-08）：G0/PR #2は統合済み。フロント修正後のPR #3/#4とmain c8e2375の
> 新規結合結果・残る競合・担当合意は [g1-revalidation.md](g1-revalidation.md) を参照。
> 以下は過去のA/B取り込み時点の記録。実Cloudの現状は未照会で、
> [G2計画](g2-readonly-survey-plan.md)は実行承認を意味しない。

2026-11-08、比較対象は main `82bf14e` と `codex/backend-a`。
以下はA側のローカル検証結果と確認案です。新しい仕様の合意や本番作業の承認を意味しません。
最新mainの決定により生成画像の24時間保存を反映。JobPayload/JobResultと承認済み秒数APIは維持。
ユーザーからBのA/B結合了承を受領。PNG・実バケット確認はB報告に基づき、Aは実環境へ接続していない。
今日の接続手順は [team-integration-guide](team-integration-guide.md)、共有ファイルの比較は [shared-file-review](shared-file-review.md)。

## 回答・対応をお願いしたい事項

| 優先 | 担当 | 食い違いと影響 | 推奨する対応・現状 |
|---|---|---|---|
| 解消 | フロント・A | 録画秒数をmy-inputから取得できなかった。 | **2026-11-08にユーザー承認済み・Aで実装**。gestureのみcountdown_seconds/record_secondsを開始時snapshotから返す。0秒・設定変更後・他担当の拒否をテスト。秒数そのものは未確定。 |
| 高 | フロント | mainの `frontend/src/api/index.ts` は `createMockBackend` 固定。実HTTP・Firebase匿名認証・Firestore購読のBackend実装がない。mainのカメラ/MediaPipeも仮入力。 | フロント担当で本物のBackendを実装し、A/B接続を確認する。Aの実応答・公開文書25例は現行TS型に代入できることを検証済みだが、ブラウザから実Aへつながった証明ではない。フロント内部は変更していない。 |
| 運用確認 | B・A | ユーザーからA/B結合の了承を受領。元worker.mainはLogSinkのまま。 | 永続入口SERVICE_ROLE=worker→api.worker:appとGameJobIO/Sinkで結合済み。実配備先・SA/URLと稼働条件は実環境検証待ち。 |
| 解消 | A・B | 画像保持期間・ライフサイクル対象が未決定だった。 | mainで生成画像24時間を決定。leave/startは録画だけ削除、画像はStorage自動削除に任せる。バケット全体の24時間設定はB報告。実体削除後は画像404、履歴・結果metadataは維持。 |
| 中 | B・A | Bの確認文書はキュー作成をA想定。承認済み役割表ではCloud Tasks/Worker基盤はB、APIからのenqueueはA。 | 基盤設定・キュー作成はB、注文の生成・送信はAを推奨。実キュー、再配送回数、Invoker/配送SA、deadlineサービスURLを共同確認する。今回リソース操作なし。 |
| 中 | フロント・A・仕様決定者 | フロント文書は受付猶予10秒・離脱30秒を提案。正本の仮値/現在のA設定は猶予5秒・離脱15秒。`config/game` の60/10/5も提案。 | 実機検証後に同じ値をAPI/Worker/期限サービスへ配布する。現状の既定値は変更していない。実Firestoreへのconfig投入も未実施。 |
| 解消 | A・B | 画像保持期間・ライフサイクル対象が未決定だった。 | mainで生成画像24時間を決定。leave/startは録画だけ削除、画像はStorage自動削除に任せる。バケット全体の24時間設定はB報告。実体削除後は画像404、履歴・結果metadataは維持。 |
| 解消 | B | 実モデルの生成画像形式が未確認だった。 | mainのconfirmation-itemsにimage/png・PNG signature・約1.2MBのB実測報告を確認。AのPNG前提を維持し変換不要。実AIスクリプトは実行せず、モデル変更時はBが再確認。 |

## ローカルで解消した接続の差異

- add/add等の11ファイルのGit競合を作業ブランチで整理。Bのworker/dataはmainとバイト一致、フロントはmain版のまま。
- `get_settings`、処理別provider、`GCP_PROJECT`/`STORAGE_BUCKET`の既存B名をA設定へ接続。自動.env読込、実認証情報の探索、ローカル実AIは有効にしていない。
- 共通StorageのB向け注入口を維持し、Firestore時刻はJSON文字列ではなくdatetimeで保存。録画削除失敗時の再試行対象を保持。
- Docker入口をAPI/Worker/期限で選択可能にした。`/health` とB標準の `/tasks/run` を保持し、OIDC audienceを宛先サービスのベースURLに統一。
- Storage Emulatorをruntimeから明示接続可能にした。別のAPI/Workerクライアントで同じ保存先を使う検証を追加。Cloud Tasksはモック。
- 結果保存後に進行が落ちるケースは、保存済み結果とprogress_outboxから再推論せず復旧。最終試行・重複配送・古いrevision・遅い裏読み取りも検証対象。

## 実環境へ進む前に残る検証

1. 了承済みの入口/IO/Sinkについて、サービスごとのSA・URL・OIDC audience・キュー設定・outbox回復の稼働条件を確定する。
2. フロントの実Backend、同意/匿名認証、状態購読、スマートフォンの録画・再生・送信時間を共同検証する。
3. Docker daemonのある環境でイメージbuild/run。この環境にはdaemonのソケットがない。
4. フロントのbuild/lintは、利用したCodex同梱Nodeがネイティブ拡張（rolldown/oxlint）をTeam ID不一致で拒否したため未検証。TypeScript検査は成功。通常のNode環境で再実行する。署名保護や依存ロックは変更していない。
5. 実Firebase/Firestore/Storage/Cloud Tasks/IAM/AI/Run/HostingとRules反映は、新たな承認を得て検証する。今回は一切接続・適用していない。

ユーザー許可によりAブランチだけ通常Pushしました。PR作成・mainへのマージは行っていません。
main起点の試験マージは競合0件・全ローカルテスト成功。詳細はbackend-a-merge-validation.md。30分ごとの監視はユーザー指示で解除済み。
テスト件数と再開方法は backend-a-progress.md を参照してください。
