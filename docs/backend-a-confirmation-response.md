# B → A 確認事項への回答案（第2フェーズ・ローカル保存）

対象：origin/main `d821bea` の docs/confirmation-items.md。
これはA側の回答記録であり、Bとの新しい合意・本番操作の承認を代行しません。
ユーザー許可によりAブランチへ通常Push済み。GitHubコメント・PR・mainマージ・実クラウド操作は行っていません。

**2026-11-08追記**：main aa9d9c5のローカル統合により、起動・設定・共有Storageの競合はA側で整理しました。
現在の未決事項は [integration-handoff](integration-handoff.md)、今日の接続情報は [team-integration-guide](team-integration-guide.md) を参照してください。以下の起動/設定未統合の記載は第2フェーズ当時の経緯です。

## 最新確認（2026-11-08、main 82bf14e）

- ユーザーからA/B結合へのB了承を受領。画像保持は24時間のStorage lifecycleへ決定。
- B報告ではバケット全体に24時間設定済み、生成はimage/png/PNG signature/約1.2MB。Aは実クラウド・実AIで再検証していない。
- 下記の画像保存期間/PNG未確認の記載は経緯。現在の未解決事項から外し、実配備時の設定確認・モデル変更時の再確認を残す。
- B提供画像のTasks/OIDC案はteam-integration-guide.mdに記録。新規キュー/SAやdeadlineサービスは作成していない。

## 先に決めたい事項

| Bの項目 | A側の回答・現状 |
|---|---|
| Firestoreの作成 | Aで設定案の準備は可能。今回は実作成・API有効化が禁止されているため未実施。リージョン・Nativeモード・作成担当を在席時に確認してから実行する。Emulatorでの検証には影響しない。 |
| プロジェクト統一・招待 | Bの記録は認識した。実プロジェクトとIAM招待は未接続・未確認。デモ環境だけを使った。Bの確認済み報告をAの実検証済みと扱わない。 |
| Runのリージョン/構成 | APIとWorkerを別サービスにする既存の設定案を維持。東京はBの候補として記録。実デプロイと不可逆な設定の確定は未承認。内部処理はIAM/OIDC認証を前提にする。 |
| advance_stepの提供 | 提供済み。backend_a.progress.advance_step(room_id, round_id)。結果保存後の再実行・クラッシュ復旧も結合テスト済み。各プロセス起動時にconfigure_progressで同じ保存先のGameServiceを注入する。 |
| Cloud Tasksの担当 | **ユーザーが承認した改訂役割表ではキュー/Worker基盤はB、APIからの登録はA**。B文書の「キュー作成A想定」は担当変更として確認が必要。今回キュー作成はしていない。 |

## shared-types §11

ユーザーは第1フェーズ前に #1〜#7を推奨どおり承認済み。#8〜#10はS1 v2.2どおり実装。
#3はmainでも合意済みと記録されているため、write_job_result→advance_stepを継続する。
#11の仕組みも実装済みだが、5秒/15秒/猶予5秒は変更可能な仮設定であり、PoC後の最終秒数と混同しない。
この回答で新しいゲームルールや共有インターフェースを確定していない。

## Bに確認したい接続点

1. **起動方法・設定の統合**：Bのworker.mainはLogSink/MemoryJobIOを使い、common.settings.get_settingsとB専用provider等の設定を必要とする。
   AのSettingsは自動.env読込やget_settingsを提供していない。共通設定を独断で書き換えず、
   今回はapi.worker_app.create_worker_app(runtime, ai)でBの実handler/jobsを注入して結合した。
   本番入口もこの構成に寄せるか、Bのmainに同じIO/Sinkを注入するかを確認したい。
2. **永続書き込みの置き場所**：BのJobSink Protocolを実装したGameJobSinkをA側接続部に置いた。
   Bのhandler/jobsを変更していない。今後Bの本番Sinkに移すなら、advance_pending/progress_outboxと
   実行期限のexecution_outboxを同じTransactionで記録する復旧条件も保持したい。
3. **共有Storageの一本化**：Bのdelete_round_assetsは画像も削除し、失敗した実体の記録も消す。
   A側は承認どおり録画だけを削除し、失敗時は記録を残して再試行する。
   BのFirestoreAssetIndexはdatetimeをJSON文字列化するが、正本はTimestampなのでA側はdatetimeを渡す。
   既存の二つを無言で上書きせず、統合時に一本化したい。
4. **録画のTTL対象**：B文書のバケット24時間削除が録画だけに適用されるか、生成画像も対象かはAで未確認。
   画像の保持期間は未決定のため、実環境のライフサイクル設定を在席時に確認したい。
5. **画像形式とSDK**：接続部は正本のPNGを前提にしている。実モデルがJPEG等を返す場合の扱いはBと要確認。
   google-genaiは依存として導入・import確認のみ。実AI・ADC・キーは使用していない。

## 再配送の前提

- AI失敗はBの実handle_jobが500/200を決定し、DBの試行回数で合計3回に制限。
- 同一試行の同時配送は追加推論を行わず、確定済み結果は再推論しない。
- 成功結果と進行outboxを同時保存するため、最終AI試行後に進行が失敗してもAから復旧できる。
- 推論中のプロセス停止も実行期限outboxで検出。残り試行があれば別名タスクを再登録し、3回消費済みなら失敗確定。
- この復旧はAの保守処理・heartbeatが動くことを前提にする。Cloud Runがゼロ台かつheartbeatもない場合の
  回復時間を保証していない。実デプロイ時のCPU/稼働条件・キュー設定はBと別途検証する。

## Git統合の範囲

Bのworker/dataと確認文書を無変更で取り込み、共有commonとpyprojectはA側の検証済み定義を維持した。
mainを変更するmergeは行っていない。2026-11-08に作業ブランチ側のadd/add競合を整理。
共通設定・Storage・依存管理の差分はintegration-handoff.mdを添えてBにレビューを依頼する。
