"""通しテストの間、AI の仕事の失敗の原因（Firestore の jobs/*.last_error）を、数秒おきに拾って表示する（読むだけ）。

再試行で成功すると last_error は消えるため、失敗している間に拾わないと原因が残らない。
使い方（通しテストを始める前に起動して、終わるまで動かす。Ctrl+C で止める）:
    ~/.venvs/gesture-relay-game/bin/python -W ignore scripts/watch_job_errors.py [秒数=300]
"""
import sys
import time

from google.cloud import firestore

client = firestore.Client(project="gesture-relay-game")
seen: set[tuple[str, str, str]] = set()
limit = float(sys.argv[1]) if len(sys.argv) > 1 else 300
t0 = time.time()
print(f"{limit:.0f} 秒間、失敗の原因を拾います（Ctrl+C で止める）")
while time.time() - t0 < limit:
    for d in client.collection_group("jobs").stream():
        x = d.to_dict()
        le = x.get("last_error")
        if not le:
            continue
        msg = (le.get("message") if isinstance(le, dict) else str(le)) or ""
        key = (d.reference.path, str(x.get("attempt")), msg[:80])
        if key in seen:
            continue
        seen.add(key)
        print(time.strftime("%H:%M:%S"), x.get("kind"), "試行", x.get("attempt"), "|", (le.get("code") if isinstance(le, dict) else ""), "|", msg[:200], flush=True)
    time.sleep(3)
print("終了")
