# A：今夜のG1統合・本番準備

> 2026-11-09更新：最新main追従と新規検証、Bの実行SA・配備報告、現在の残条件は [A再開状況](a-resume-status.md) を参照。以下の未確定/レビュー待ち等は当時の記録です。

締切：11/10 17:00 JST。2026-11-08に着手。実Cloudの読取/ログインを含むアクセスは一切なし。
元Aの未追跡文書、main、フロント/Bソースを保全。A準備はcodex/backend-a-maintenance（PR #6起点）の別worktree。

**最新：PR #6は個別承認後に通常merge済み。main150df95、ソースbranchは保持。**
#3と新mainの隔離merge a36ea00は競合なし、新規Emulator142/Rules5/Node14/3人成功。
その後の保守追加テストで既存同時提出競合を検出し、独立Draft #8に分離（修正単体もEmulator142/Rules5成功）。
#7の150秒子process上限は19保守テスト成功。#8併用では全161/Rules5/3人成功だが、単独#7の全成功とは扱わない。
[時間枠の実装・残条件](maintenance-time-budget.md)を参照。下記の旧段階の検証結果と区別する。

## 実施可能・完了したもの

- 最新GitHub取得：main c8e2375、#3 frontend 3db187b、#4 frontend-effects dd6794b、#6 ef3bbe2。
  作業中に競合解消headが到着：#3 **93717e1**、#4 **47fc72e**。両方のfrontend/差分ゼロをAでも確認し、新headで再実行した。
- #6の最終差分8ファイルを再確認。frontend/とB実装・共通型への変更なし。API credentials/tokenはharnessへ渡さず、
  loopback/demo-project/AnonymousCredentials/MockAIだけを使う。生成module/log/Emulator設定はGit対象外。
  repo内Actions workflowはなし。外部Apps/Webhooks/Cloud連携は未確認なので、安全確認済みとはしない。
- 保守API：api.internal:app専用POST /internal/maintenance、既存OIDC検証、1回の保守pass。
  API/WorkerにはこのHTTP入口を追加せず、Bのworker/main.pyを変更しない。deadline構成だけbackground loopを停止。
- 未認証/誤SA、1 pass、重複/並行、write_job_result後の停止、delivery失敗、捨てられた実行receipt、録画cleanupの復旧を13テストで検証。
  保存済み画像/生成回数の維持を確認。局所エラーは永続outboxで次passへ持越す。
- API/deadlineの環境変数、IAM境界、配備依存、ロールバック、Hosting/Auth確認票を
  [backend-a-deployment-runbook.md](backend-a-deployment-runbook.md) と未適用YAMLに整理。
- G2計画を最新のB承認報告へ照合。報告とAの現物確認、方針決定と実作成を分離して更新。

## G1：PRごとの判定と順番

| PR | 取得時の状態 | 技術上の残件 | 人間承認 |
|---|---|---|---|
| #6 | merged、commit150df957f6aa11cb75e8d5b383791577a7f0e23e | 承認bedcc62/head ef3bbe2を照合して通常merge。元branch保持 | 実施済み。承認を他PRへ拡張しない |
| #3 | 93717e1、open。新mainとのlocal結合成功 | frontend所有側のmain取り込み待ち。同時提出の既知リスク#8を確認してから直前状態を再評価 | #3単独の承認待ち |
| #4 | 47fc72e、open、**base=frontend**、formal reviewなし。直近のGitHub mergeabilityは再計算中unknown | ローカル順序mergeは競合なし。#3 main統合後、フロントがbaseをmainへ変更し差分/履歴を確認 | #4単独の承認待ち。frontend向け判定をmain向け判定に流用しない |

順番は **#6 → #3 → #4**。#6によりmainの古いB出所testが直り、harnessが使える。
#3はそれを取り込んでからfront側で競合を解消。#4は#3に依存し、現在のbaseはmainではない。
GitHubのbranch protection/外部デプロイ経路は未確認。PR単位の直前状態確認と人間承認を必須とし、今回は実mergeしない。
保守APIのPRは#6へstackしたまま。mainへのretargetは未実施で、#8の確認後に差分/全suiteを再確認する。#3/#4の製品コードを混ぜない。

ローカルだけの順序mergeを実施：main c8e2375 → #6 f5f4732 → #3 64fe49d → #4 beac374。
最終treeのfrontend/は47fc72e、Backend/Worker/テスト/toolsは#6と一致。元main/remoteには反映していない。
[フロントの順序・Hosting同意と新head](https://github.com/trtrna/gesture-relay-game/pull/3#issuecomment-6721541340)も確認済み。

## 担当の返信待ち

- フロント：新headと順序/Hosting同意は受領済み。今後#6/#3承認・統合後の追従と#4のbase変更はフロント担当。
  ブラウザ/React effect/実録画・iPhone/HTTPS、購読errorの実UI表示は未確認のまま共有済み。
- B：PR #6コメント6721444452。Schedulerが既存tasks-invoker名義でdeadlineベースaudを使う案、
  Worker/deadline/APIのenqueue/actAs/Invokerの境界、attempt deadline・retryを照合。
  別Scheduler SAを許可する設定は未追加。合意前に共有Settings/Workerを変更しない。

## 人間の承認待ち

- #6/#3/#4および保守API PRのmainマージはそれぞれ別承認。
- G2読取調査：project/region/billing範囲・期間、既存調査者/認証/読取権限、限定保存先を指定して明示承認。
- SA/IAM、API有効化、Run/Worker/Hosting配備、Tasks/Scheduler変更、実AI、課金は別途承認。
- 本番のconfig/gameの秒数、Auth匿名有効化/Hostingドメイン追加、初回サービスのbootstrap/ロールバック方針。

## 検証の範囲

保守追加ブランチ：offline **152 passed / 3 skipped**、Emulator **155 passed（31.34秒）**、Rules **5 passed**。
main c8e2375 + #6 + 今夜の保守変更が対象。現行#3 factory（ローカルmain結合3d9aefa）で14 API/B MockAI/3人完走も新規成功。
G1/#6自体は保守変更を混ぜず別worktreeで**142 passed（22.53秒）/Rules5 passed**。
93717e1/47fc72eそれぞれで14 API/4購読/B MockAI/3匿名UIDの一巡、8エラー注入ケース、2状態モデルが新規成功。
新headのfrontend tests **14/24 passed**、lint/tsc/Emulator build成功（SKIP_MEDIAPIPE=1）。
これらはテスト対象SHAを記録した今回の新規結果。将来headが変われば再評価する。
A新規コードのruff/format成功。既存B worker3 lint/test_odai format1は未変更で残る。
Docker CLIは存在するがlocal daemon socketなしでbuild/run未検証。Cloud実設定・実AI・実機も未検証。

## 次の手順

1. git status/logと本書、backend-a-progressを確認。main/PR #3/#4/#6とコメントをread-only取得。
2. 新headがあれば対象SHA/merge差分を確認し、tools/run_g1_emulator_checks.shとfrontend testsを再実行。
3. 不変headの同じテストを返信待ちだけで繰り返さない。独立タスクがなくなれば停止し、手動再開を待つ。
4. G2/配備/実マージへ自動移行しない。ブランチの最後のコミットはgit log -1を正本とする。
