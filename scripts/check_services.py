"""配備した3つのサービスに、自分の身元（gcloud）で /health を呼んで確認する（鍵は表示しない）。"""
import subprocess
import urllib.error
import urllib.request

P, R = "gesture-relay-game", "asia-northeast1"
token = subprocess.run(["gcloud", "auth", "print-identity-token"], capture_output=True, text=True, check=True).stdout.strip()
for s in ("worker", "gesture-relay-deadlines", "gesture-relay-api"):
    url = subprocess.run(["gcloud", "run", "services", "describe", s, "--project", P, "--region", R, "--format=value(status.url)"],
                         capture_output=True, text=True, check=True).stdout.strip()
    for path in ("/health", "/healthz"):
        req = urllib.request.Request(url + path, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                print(s, path, r.status, r.read()[:80])
            break
        except urllib.error.HTTPError as e:
            print(s, path, e.code)
