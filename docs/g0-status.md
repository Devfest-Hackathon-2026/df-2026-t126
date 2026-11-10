# G0：最新A/B統合と最終マージゲート（2026-11-08）

## 最新：ユーザーの最終承認受領

ユーザーから現在未デプロイ確認に基づくPR #2最終マージ承認を受領。保留を解除し、コードマージだけを実行する。
直前にmainの6c45990→a0cc2ef更新を検出したためマージを実行せず再統合し、下記テストを全て再実行した。
競合はworker/ai/__pycache__/real.cpython-312.pycのmodify/deleteのみ。生成物を追跡解除し、Bソースは最新mainと一致。
Bの別モデル/ロケーションfallbackと切替先で待たない挙動を維持し、Aのテスト用fake cacheを新しいキーへ適合した。
Webhooks/Apps設定を確認済みとは扱わず、Cloud接続・変更・実AI・再デプロイ・G1マージは実行しない。

## 完了した範囲

- 最新main `a0cc2ef` を `codex/backend-a`（開始時 `ef9ca5f`）へ取り込み。内容競合なし。
- Bの429バックオフ（6秒・12秒）、Vertex/Developer切替、最大60件/小数3桁の座標前処理、プロンプト調整を保持。
  worker/dataのソースは取得mainとバイト一致し、出所をbackend-b-source.jsonへ更新した。
- Bの新規テストも実行。Bテスト2ファイルはformatのみ変更、ロジックは維持。
- mainに混入した10個の生成済みcpython-312.pycだけをGit追跡から解除。ソースとディスク上のcacheは保持。
- 新規結合テスト：Aの座標受理→数値順/重複無害化→Bの前処理→結果保存、BのSDK内部429→provider切替→Aの1回確定→二重配送を検証。
  AI通信はすべてmock。実モデル/キー/ADCを使用していない。
- B同意コメントとA返答をdocs/ab-coordination.mdへ記録。JobPayload/JobResultとwrite_job_result→advance_stepを維持。

## 検証結果

| 検証 | 結果 |
|---|---|
| オフラインpytest | **136 passed / 3 skipped** |
| Auth/Firestore/Storage Emulator pytest | **139 passed**（24.59秒） |
| Security Rules | **5 passed** |
| 匿名3UID・実HTTPの3人ゲーム | **成功**。API＋B実handler/jobs＋MockAI＋Firestore/Storage Emulator、結果・帰還まで |
| 429/provider/前処理 | Bの新テストとA/B接続テスト成功。SDKはfake、ネットワーク禁止 |
| 静的検査 | ruff check/format 44ファイル、compileall、diff検査成功 |
| 依存・フロント境界 | uv lock/check、66パッケージ整合、実応答/公開文書25例のTS型代入成功 |

G1とポートを分離：G0はFirestore18080/Auth19099/Storage19199/hub14400/logging14500/websocket19150。
すべてloopback、demo-gesture-relay、匿名/ダミー認証。Emulator停止まで確認。設定/ログは.tools/g0-*（非追跡）。
エミュレーターのlifecycleは実行されないため画像削除テストは模擬。実Cloud動作の証明ではない。
Docker daemon、実AI、実Cloud、実機ブラウザは今回検証していない。

## 最終マージ条件の確認

| 条件 | 確認結果 |
|---|---|
| 最新main取込・競合・テスト | 上記のmainを取り込み、未解消競合なし、主要テスト成功 |
| A/B契約 | Bの明示同意を確認、入口/Storage/担当/OIDC/入力を維持 |
| GitHubレビュー | PR #2のB同意コメントあり。正式review submissionsは0件 |
| 保護条件 | branches/mainはprotected=false、rulesetsは空。ただしprotection詳細APIは403で取得できない |
| リポジトリ内CI/デプロイ | main/Aに.githubのworkflow等はない。deploy_worker.shは明示実行のスクリプトで、実行していない |
| GitHub実行結果 | 既存PR headのcheck-runs/statusは0件。status=pendingは0件の集計であり、CI成功とは扱わない |
| Webhooks/Installed Apps | **未確認**。GitHubコネクターの該当endpointは未対応。FirefoxのComputer Useは利用許可なしで拒否 |
| 外部Cloud側の連携 | Bの読み取り確認報告を受領。Aから実Cloudへ確認アクセスしていない |

**以前の保留時の結論**：未確認の間は最終マージだけを停止した。その後、上記のユーザー最終承認を受領。
ユーザー指示により、Webhooks/Installed Appsを確認できない状態を安全と推測しない。
最終承認後は直前確認してReady化・通常マージする。自動マージを有効化せず、G2の実Cloud/デプロイへ進まない。

管理者に必要な確認は、リポジトリSettingsのWebhooks/Installed GitHub Appsと外部CIに、main pushで実Cloud操作を起動する連携がないことの記録。
設定変更を依頼しているのではない。確認後は改めてmain/PR head/保護/レビュー/チェックを読み直し、変更があれば再統合・テストする。
この文書は未来のmainマージを自動実行する予約ではない。

## G1との並行境界

- G1は別worktree `.tools/g1-worktree`、別ブランチ `codex/frontend-real-backend`。
- API契約変更なし。G1はG0のmainマージを待たず実HTTP BackendとEmulator結合を実装する。
- G1変更をPR #2/G0作業ツリーへ取り込まない。G1のmainマージは許可されていない。
- G0/G1共通の禁止：実Cloud、本番認証情報、実AI、公開トンネル/公開サーバー、未承認IAM・課金・デプロイ。
- G0開始コメント：https://github.com/trtrna/gesture-relay-game/pull/2#issuecomment-6717556047
- G1の完了・未検証項目はG1 worktreeの独立進捗文書で報告する。現時点で実機の完了とは扱わない。

既存の未追跡docs/ab-agent-coordination.mdは他の作業として保全し、このコミットには含めない。
