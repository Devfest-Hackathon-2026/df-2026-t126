"""通しテストのあとに、本番のログと部屋の状態をまとめて見る（読むだけ）。

使い方（リポジトリの直下で）:
    ~/.venvs/gesture-relay-game/bin/python scripts/check_run.py            # 直近30分
    ~/.venvs/gesture-relay-game/bin/python scripts/check_run.py 60         # 直近60分

見るもの:
  1. API の通信（件数、HTTP の結果、503 の数、窓口ごとの速さ）
  2. Worker の AI の仕事（成功・失敗）
  3. 直近に作られた部屋の結果（finished / failed と、失敗の理由）
鍵やトークンは、表示しない（gcloud の認証は、この PC の設定をそのまま使う）。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

PROJECT = "gesture-relay-game"


def gcloud_logs(filter_: str, limit: int = 3000) -> list[dict]:
    cmd = ["gcloud", "logging", "read", filter_, "--project", PROJECT, "--limit", str(limit), "--format", "json"]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        print("ログを読めませんでした:", out.stderr.strip().splitlines()[-1:] or "")
        return []
    return json.loads(out.stdout or "[]")


def seconds(latency: str | None) -> float:
    return float(latency.rstrip("s")) if latency else 0.0


def normalize(path: str) -> str:
    path = re.sub(r"https://[^/]+", "", path).split("?")[0]
    path = re.sub(r"/(rooms|rounds)/[A-Za-z0-9]{10,}", r"/\1/X", path)
    return re.sub(r"/assets/[a-f0-9]+", "/assets/H", path)


def api_summary(since: str) -> None:
    logs = gcloud_logs(
        'resource.type="cloud_run_revision" AND resource.labels.service_name="gesture-relay-api" '
        f'AND httpRequest.requestUrl:"/api/" AND timestamp>="{since}"'
    )
    print("■ 1. API の通信")
    if not logs:
        print("  通信は、ありませんでした。")
        return
    status = Counter(str(x["httpRequest"].get("status")) for x in logs)
    print(f"  合計 {len(logs)} 件 / 結果: " + ", ".join(f"{k}={v}" for k, v in sorted(status.items())))
    n503 = status.get("503", 0)
    print(f"  503（受付が満員で断られた）: {n503} 件 {'✅ なし' if n503 == 0 else '⚠ あり'}")
    by = defaultdict(list)
    for x in logs:
        h = x["httpRequest"]
        by[f"{h.get('requestMethod')} {normalize(h.get('requestUrl', ''))}"].append(seconds(h.get("latency")))
    print("  窓口ごとの速さ（件数 / 平均 / 最大、秒）。ふだんは 0.5 秒前後が目安")
    for key, vals in sorted(by.items(), key=lambda kv: -max(kv[1])):
        flag = " ⚠ 遅い" if max(vals) > 5 else ""
        print(f"   {key[:52]:52} {len(vals):4d} / {sum(vals)/len(vals):5.2f} / {max(vals):5.2f}{flag}")
    auth = status.get("401", 0) + status.get("403", 0)
    if auth:
        print(f"  ⚠ 認証エラー（401/403）: {auth} 件（ログインの期限切れの可能性）")


def worker_summary(since: str) -> None:
    logs = gcloud_logs(
        'resource.type="cloud_run_revision" AND resource.labels.service_name="worker" '
        f'AND textPayload:"job=" AND timestamp>="{since}"'
    )
    print("\n■ 2. Worker（AI の仕事）")
    jobs = []
    for x in logs:
        m = re.search(r"job=(\S+) kind=(\S+) attempt=(\d+) ok=(\w+) error=(\S+)", x.get("textPayload", ""))
        if m:
            jobs.append(m.groups())
    if not jobs:
        print("  AI の仕事は、ありませんでした。")
        return
    ok = sum(1 for j in jobs if j[3] == "True")
    print(f"  合計 {len(jobs)} 回 / 成功 {ok} / 失敗 {len(jobs) - ok}（失敗は、自動で再試行されます）")
    for kind in sorted({j[1] for j in jobs}):
        rows = [j for j in jobs if j[1] == kind]
        bad = Counter(j[4] for j in rows if j[3] != "True")
        print(f"   {kind:12} {len(rows):3d} 回 / 失敗の理由: {dict(bad) if bad else 'なし'}")


def rooms_summary(since_dt: datetime) -> None:
    print("\n■ 3. 直近に作られた部屋の結果")
    try:
        from google.cloud import firestore
    except ImportError:
        print("  google-cloud-firestore が無いので、部屋は見られません（venv の python で実行してください）")
        return
    client = firestore.Client(project=PROJECT)
    rows = []
    for r in client.collection("rooms").stream():
        d = r.to_dict()
        created = d.get("created_at")
        if created and created >= since_dt:
            rows.append((created, d))
    if not rows:
        print("  この期間に作られた部屋は、ありません。")
        return
    for created, d in sorted(rows, key=lambda x: x[0]):
        t = created.astimezone(timezone(timedelta(hours=9))).strftime("%H:%M")
        status = d.get("status")
        mark = {"finished": "✅", "failed": "❌", "playing": "⏳", "waiting": "…"}.get(status, "?")
        print(f"   {t} 部屋 {d.get('join_code')} {mark} {status}" + (f"（理由: {d.get('fail_reason')}）" if d.get("fail_reason") else ""))
    print("  ✅ finished = 結果画面まで進めた / ❌ failed = 途中で止まった / … waiting = ゲームが始まっていない")


def main() -> None:
    minutes = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    since_dt = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    since = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"通しテストの確認（直近 {minutes} 分、{since_dt.astimezone(timezone(timedelta(hours=9))).strftime('%H:%M')} 以降）\n")
    api_summary(since)
    worker_summary(since)
    rooms_summary(since_dt)


if __name__ == "__main__":
    main()
