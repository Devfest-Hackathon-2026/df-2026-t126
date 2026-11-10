"""Real loopback HTTP smoke: Auth/Firestore/Storage Emulators + B mock Worker.

Requires RUN_FIRESTORE_EMULATOR_TESTS=1. Starts/stops only its own local API
process. Does not log tokens or use production credentials. Run after pytest.
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend_a.runtime import localhost_endpoint  # noqa: E402
from tests.conftest import video_bytes  # noqa: E402


def main():
    if os.environ.get("RUN_FIRESTORE_EMULATOR_TESTS") != "1":
        raise ValueError("Explicit local Emulator test mode is required")
    for name in (
        "FIRESTORE_EMULATOR_HOST",
        "FIREBASE_AUTH_EMULATOR_HOST",
        "FIREBASE_STORAGE_EMULATOR_HOST",
    ):
        localhost_endpoint(os.environ.get(name, ""))
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("GOOGLE_APPLICATION_CREDENTIALS", "FIREBASE_TOKEN")
    }
    env.update(
        RUNTIME_MODE="emulator",
        ENABLE_CLOUD="false",
        AI_MODE="mock",
        PROJECT_ID="demo-gesture-relay",
        BUCKET_NAME="demo-gesture-relay.appspot.com",
        CORS_ORIGINS='["http://localhost:5173"]',
    )
    # The explicit Firebase Storage endpoint is used by both API and Worker.
    env.pop("STORAGE_EMULATOR_HOST", None)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    store = firestore.Client(project="demo-gesture-relay", credentials=AnonymousCredentials())
    store.document("config/game").set(
        {"text_seconds": 60, "countdown_seconds": 3, "record_seconds": 5}
    )
    log = ROOT / ".tools/team-http-smoke.log"
    log.parent.mkdir(exist_ok=True)
    with (
        log.open("w") as output,
        httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=15) as client,
    ):
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "api.local:build_local_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
            ],
            cwd=ROOT,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            until = time.monotonic() + 20
            while True:
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                if process.poll() is not None or time.monotonic() >= until:
                    raise RuntimeError(f"Local API failed to start; inspect {log}")
                time.sleep(0.1)
            tokens = []
            auth = localhost_endpoint(env["FIREBASE_AUTH_EMULATOR_HOST"])
            for _ in range(3):
                response = httpx.post(
                    f"http://{auth.netloc}/identitytoolkit.googleapis.com/v1/accounts:signUp?key=demo-key",
                    json={"returnSecureToken": True},
                    trust_env=False,
                )
                response.raise_for_status()
                tokens.append(response.json()["idToken"])

            def request(method, path, who=0, expected=200, **kwargs):
                response = client.request(
                    method, path, headers={"Authorization": f"Bearer {tokens[who]}"}, **kwargs
                )
                assert response.status_code == expected, (method, path, response.status_code)
                return response

            def post(path, who=0, body=None, expected=200):
                return request(
                    "POST", path, who, expected, json={"request_id": str(uuid4()), **(body or {})}
                ).json()

            room = post("/api/rooms", body={"name": "A", "consented": True})
            room_id = room["room_id"]
            for who, name in ((1, "B"), (2, "C")):
                post(
                    "/api/rooms/join",
                    who,
                    {"name": name, "consented": True, "join_code": room["join_code"]},
                )
            for who, role in enumerate("ABC"):
                post(f"/api/rooms/{room_id}/role", who, {"role": role})
            round_id = post(f"/api/rooms/{room_id}/start", expected=202)["round_id"]
            base = f"/api/rounds/{round_id}"

            def wait_for(path, who, predicate):
                until, heartbeat = time.monotonic() + 30, 0
                while time.monotonic() < until:
                    if time.monotonic() >= heartbeat:
                        for uid in range(3):
                            request("POST", f"/api/rooms/{room_id}/heartbeat", uid)
                        heartbeat = time.monotonic() + 3
                    response = client.get(path, headers={"Authorization": f"Bearer {tokens[who]}"})
                    if response.status_code == 200 and predicate(response.json()):
                        return response.json()
                    time.sleep(0.1)
                raise AssertionError(f"Local game did not progress: {path}")

            first = wait_for(base + "/my-input", 0, lambda v: v["step_index"] == 1)
            assert request(
                "GET", base + "/assets/" + first["input"]["asset_id"]
            ).content.startswith(b"\x89PNG")
            post(base + "/steps/1/submit", body={"text": "犬"}, expected=202)
            gesture = request("GET", base + "/my-input", 1).json()
            assert (gesture["countdown_seconds"], gesture["record_seconds"]) == (3, 5)
            session = post(base + "/gesture/start", 1)["gesture_session_id"]
            post(base + "/gesture/finish", 1, {"gesture_session_id": session}, 202)
            request("GET", base + "/my-input", 2, 403)
            video = request(
                "POST",
                base + "/gesture/video",
                1,
                data={"gesture_session_id": session, "request_id": str(uuid4())},
                files={"file": ("sample.mp4", video_bytes(), "video/mp4")},
            ).json()
            assert (
                request("GET", base + "/my-input", 2).json()["input"]["asset_id"]
                == video["asset_id"]
            )
            post(base + "/steps/3/submit", 2, {"text": "犬"}, 202)
            final = wait_for(base + "/history", 2, lambda v: v["round_status"] == "finished")
            assert final["result"]["ai_conclusion"] and len(final["steps"]) == 6
            for who in range(3):
                assert request("GET", base + "/history", who).json()["round_status"] == "finished"
                post(f"/api/rooms/{room_id}/leave", who)
            print(
                "PASS: three anonymous users, real HTTP API, B mock Worker, shared Emulator storage, final history"
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
