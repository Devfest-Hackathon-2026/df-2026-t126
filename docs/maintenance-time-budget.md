# PR #7：保守3分未満のローカル対応

> 2026-11-09更新：最新main追従と新規検証、Bの実行SA・配備報告、現在の残条件は [A再開状況](a-resume-status.md) を参照。以下の未確定/レビュー待ち等は当時の記録です。

Bのレビュー6722138731とA回答6722216394を受けた実装。実Cloudのログイン/読取/配備/実AIは未実行。

## 実装

- Cloud runtimeだけ、固定command `python -m backend_a.maintenance_worker` に1 passを委譲。
  許可した非秘密設定をstdinで渡し、API key/token/credentials環境変数を子へ渡さない。
  子は既存runtime SAを使う設計で、AI clientは生成しない。新たなSA/権限/共有Settings項目はない。
- 子はruntimeを1回構築しmaintenance_onceを1回実行して終了。SDK clientを親からfork共有しない。
- subprocess.run(timeout=150)を使い、超過時は子をkillして回収し、親は500を返す。
  Python threadのキャンセルだけでSDK処理を残す方法は使わない。
- 同一Cloud app instanceの同時起動をlockで拒否し500で再試行。別instanceとの冪等性は既存transaction/outboxが担当。
- local/emulatorではMemoryTasksの配送を親に保持するためin-processを維持。Cloud branchはmockで検証し、実Google SDK接続をしない。
- 未適用Runひな型は180秒へ変更。Scheduler attemptDeadline=180秒、Tasks HTTP既定600秒/最大1800秒を区別する。
  Scheduler/OIDC/Run設定は一切適用していない。

## ローカル検証と限界

- 保守19ケース成功（従来13＋6）。Cloud branchのconfig/env制限、1 pass、重複拒否/例外後lock解除、異常終了を確認。
- 実際のローカルsleep子プロセスを2秒設定で打ち切り、PIDが存在しないことを確認。
  この子にはSDKも資格情報もない。既定150秒指定は別のテストで確認。
- Cloud childのruntime構築はmock化して呼出数とAI modeを確認。実Cloud上のmetadata認証/Firestore/Tasksは未検証。
- 既存outboxテストでwrite_job_result後の停止、二重配送、execution receipt、cleanup復旧を維持。
  実Cloud子プロセスをcommit途中でkillする試験は未実施で、成功したと扱わない。
- offline158 passed/3 skipped。最初のEmulatorは既存同時提出テストのロック競合で1 failed/160 passed。
  保守テスト自体の失敗ではないが、全体成功とは扱わない。
- 独立したFirestoreローカルTransaction入場制御修正を併用した再検証では
  **Emulator161 passed（12.33秒）/Rules5 passed、14 API/B MockAI/3人完走**。
  この161件はその修正を含む組合せの結果であり、PR #7単独headの全成功ではない。

SDKの単一操作が長引いても子processを終了できる構造を用意したが、
process生成にかかる時間はrunのtimeoutでは中断できず、Run cold start・OS scheduling・終了処理にも時間がかかる。
**実環境のリクエスト全体が3分未満である保証はまだない。**
負荷/冷起動/SDK待ち/途中commitと復旧を承認された実環境で測定するまではB条件を完全充足と宣言しない。

## 未実施の次手順

1. Bが150秒child/180秒Run案、runtime SAでの子client初期化、再配送/滞留監視をレビュー。
2. Transaction修正の独立PR #8（f7b7b40）をレビュー。mainへ入った後、PR #7のbaseと最新mainを更新して全suiteを再実行。
3. G2の読取・将来の配備/負荷/実OIDC試験はそれぞれ人間承認。今回は実マージ/クラウド操作をしない。

根拠：[Python subprocess.run](https://docs.python.org/3.11/library/subprocess.html#subprocess.run)。
Popen.communicate単体はtimeoutで自動killしないため、それとrunの挙動を混同しない。
