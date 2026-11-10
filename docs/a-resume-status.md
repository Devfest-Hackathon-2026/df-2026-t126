# A再開・検証結果（2026-11-09 JST）

## 基点と今回の検証

main 62bd65238feb5ecce16beb34f224881d0d8eee3e、PR #7旧head1329740。
隔離したcodex/a-resume-maintenanceへmainを競合なく統合（0ea2e1c）。
PR #4対象はee3d965cfc5fea526b55e00045910554e780d2a3。
15ba1be以降の製品差分はGesturePocの録画を約5秒から8秒へ揃える変更だけ。

- PR #7単独＋最新main：offline163 passed/3 skipped（5.94秒）。
- Auth/Firestore/Storage Emulator：166 passed（12.70秒）、Rules5 passed。
- 最新#4のrealBackendで14 API・4購読・匿名3UID・B実handler/jobs+MockAI・PNG/MP4・結果/退出・heartbeat・401同一body再送が成功。
- 購読error8件・状態モデル2件も成功。実UI/React DOMの試験ではない。
- #4 frontend32件成功、型検査・mock/Emulator build成功。MediaPipeは既存依存を使い、モデル取得はskip。500KB chunk警告あり。
- A/api/common/testsのruff check成功。formatは47件成功、main由来tests/test_odai.pyの1件は残る。
- 初回Emulatorはrules-unit-testingの依存リンク不足で中断。ローカル既存依存へ接続して再実行し、上記成功を確認。
- Cloudログイン/実読取/実AI/IAM/配備/実config/マージは今回未実施。

## 新しい受領情報（Aによる実照会とは区別）

BのPR #7コメント6723869638：API実行SAはapi-runtime@gesture-relay-game.iam.gserviceaccount.com、
期限・保守はdeadline-runtime@gesture-relay-game.iam.gserviceaccount.com。
付与権限と配備済みrevisionはmainのdocs/handoff-2026-11-09.mdとpending-approvals #10–12のB報告を参照。
Aが実IAM/現revisionを再確認した証拠ではない。
Bは150秒子process方式へ同意済み（6723006930）。旧文書のレビュー待ち/SA未確定は過去の状態。

## 保守の判断と実環境の残条件

現例はmax instances=2を維持。インスタンス内lockを分散lockとは扱わない。
既存Transaction/outboxの冪等性を利用する設計で、ローカル重複・回復試験は成功。
実Cloud複数instanceでの停止/重複は未検証であり、その保証を今回の結果から主張しない。
配備後B側で、子processのmetadata ADC、cold start込み180秒余裕、timeout後500と次pass回復、
重複配送・複数instanceの結果、録画cleanup/画像保持を確認する。
HTTP200は全outbox処理完了を意味しない。deadline再配備とScheduler作成は別承認。

## 15秒準備・8秒録画：未適用の変更案

#4 mock/fallbackは15/8、一方common.models.GameConfig既定と仕様例は3/5。
実APIのmy-inputは開始時config snapshotを返すため、フロントだけの変更では実ゲームは15/8にならない。
推奨案：人間確認後、共通既定・仕様例・共有型例・該当fixtureを15/8に揃え、
本番config/gameへの反映は別にBと承認/実施を調整する。進行中roundは変更しない。
今回は設定を変更していない。今回のHTTP一巡は既定3/5であり15/8の実画面成功ではない。
過去のA合成fixtureでは8秒MP4/WebM受理・9秒拒否を確認済み。
フロント報告6723834735では疑似カメラMP4 419154 bytes/7.81秒・モック新UI3人一巡成功。
実カメラ/iPhoneのサイズ・送信時間、新UI→実API→人C再生の確認は残る。

## 次の判断

1. #7へ検証済みmain追従を反映しbaseをmainへ更新。通常マージは人間の個別判断。
2. #4は新UIのHTTP送信/録画・実機の証拠を所有者と揃え、個別マージ判断。
3. Issue #5はcodex/b-contract-test-scopeの独立差分。契約入口3件とJob schemaを固定し、
   プロンプト/お題/AI調整のhashは出所情報に留める。144 passed/3 skipped、対象ruff/format成功。
4. API公開・Hosting・Scheduler・実クラウド試験は本書で承認しない。
