# Issue #5：Bの契約検査と出所情報の分離

2026-11-09。main 62bd652から独立したローカル差分。
A/BがIssue #5で同意した案1を実装する。

- バイト一致を必須にする対象はworker/handler.py・jobs.py・main.py。
- JobPayload/JobResult/JobDoc/ErrorInfoのJSON Schema一致検査は維持する。
- 13ファイルの既存ハッシュとrevisionは過去の取込元の記録として保持する。
  プロンプト・お題・AIクライアント等の現在値との一致は要求しない。
- 実Worker結合テスト、前処理、AI retry等の振る舞いの検査は削除しない。
- entry pointやJob schemaを合意して変更する場合は、従来どおり出所記録と契約をレビューする。

実装・共有型・Bデータへの変更なし。PR #7へ混ぜず、別差分としてレビューする。
