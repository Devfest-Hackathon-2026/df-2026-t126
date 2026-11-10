import os
import socket
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import uuid4

import av
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from backend_a.auth import DenyInternalAuth, LocalAuth
from backend_a.game import GameService, root
from backend_a.runtime import Runtime
from backend_a.store import MemoryStore
from backend_a.tasks import MemoryTasks
from common.models import JobPayload, JobResult
from common.settings import Settings
from common.storage import AssetStorage, MemoryBlobs


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    """Accidental cloud/credential requests must fail, even on developer machines."""

    def deny(*args, **kwargs):
        raise AssertionError("Network access is forbidden in unit tests")

    connect = socket.socket.connect
    create_connection = socket.create_connection

    def local_connect(sock, address):
        if not isinstance(address, tuple) or address[0] not in {"localhost", "127.0.0.1", "::1"}:
            deny()
        return connect(sock, address)

    def local_connection(address, *args, **kwargs):
        if address[0] not in {"localhost", "127.0.0.1", "::1"}:
            deny()
        return create_connection(address, *args, **kwargs)

    emulator = os.environ.get("RUN_FIRESTORE_EMULATOR_TESTS") == "1"
    monkeypatch.setattr(socket.socket, "connect", local_connect if emulator else deny)
    monkeypatch.setattr(socket, "create_connection", local_connection if emulator else deny)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 7, 12, tzinfo=UTC)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


class Harness:
    def __init__(self):
        self.clock, self.store, self.tasks = Clock(), MemoryStore(), MemoryTasks()
        if os.environ.get("RUN_FIRESTORE_EMULATOR_TESTS") == "1":
            import httpx
            from google.auth.credentials import AnonymousCredentials
            from google.cloud import firestore

            from backend_a.runtime import localhost_endpoint
            from backend_a.store import FirestoreStore

            endpoint = os.environ.get("FIRESTORE_EMULATOR_HOST", "")
            localhost_endpoint(endpoint)
            project = "demo-gesture-relay"
            httpx.delete(
                f"http://{endpoint}/emulator/v1/projects/{project}/databases/(default)/documents",
                timeout=30,
                trust_env=False,
            ).raise_for_status()
            self.store = FirestoreStore(
                firestore.Client(project=project, credentials=AnonymousCredentials())
            )
        self.settings = Settings()
        self.assets = AssetStorage(self.store, MemoryBlobs(), self.clock)
        self.game = GameService(self.store, self.assets, self.tasks, self.settings, self.clock)
        self.runtime = Runtime(self.game, LocalAuth(), DenyInternalAuth(), self.settings)
        self.client = TestClient(create_app(self.runtime), raise_server_exceptions=False)

    def post(self, path, uid="a", body=None, expected=200):
        response = self.client.post(
            path,
            headers={"Authorization": f"Bearer local:{uid}"},
            json={"request_id": str(uuid4()), **(body or {})},
        )
        assert response.status_code == expected, response.text
        return response.json()

    def get(self, path, uid="a", expected=200):
        response = self.client.get(path, headers={"Authorization": f"Bearer local:{uid}"})
        assert response.status_code == expected, response.text
        return response.json()

    def lobby(self):
        room = self.post("/api/rooms", body={"name": "A", "consented": True})
        self.room_id = room["room_id"]
        self.code = room["join_code"]
        for uid in ("b", "c"):
            self.post(
                "/api/rooms/join", uid, {"name": uid, "consented": True, "join_code": self.code}
            )
        for uid in ("a", "b", "c"):
            self.post(f"/api/rooms/{self.room_id}/role", uid, {"role": uid.upper()})
        return self.room_id

    def start(self):
        if not hasattr(self, "room_id"):
            self.lobby()
        result = self.post(f"/api/rooms/{self.room_id}/start", expected=202)
        self.round_id = result["round_id"]
        self.base = root(self.room_id, self.round_id)
        return self.round_id

    def doc(self, suffix=""):
        return self.store.atomic(lambda tx: tx.get(self.base + suffix))

    def step(self, index):
        return self.doc(f"/steps/{index}")

    def pending_job(self, kind, index=None):
        jobs = self.store.atomic(lambda tx: tx.list(f"{self.base}/jobs"))
        job_id, job = next(
            (key, value)
            for key, value in jobs
            if value["kind"] == kind and value["status"] not in ("done", "failed")
        )
        return JobPayload(
            job_id=job_id,
            kind=kind,
            room_id=self.room_id,
            round_id=self.round_id,
            step_index=index,
            revision=job["revision"],
        )

    def complete(self, kind, index=None, result=None):
        """Test-only B substitute, NOT a production Worker implementation.

        Emulates B's write_job_result transaction then calls A's advance_step.
        No AI, prompts, real odai source or retries are implemented here.
        """
        payload = self.pending_job(kind, index)
        if result is None:
            if kind == "image_gen":
                asset = self.assets.save_asset(
                    self.room_id, self.round_id, "image", index, b"fixture-image", "image/png"
                )
                result = JobResult(ok=True, asset_id=asset)
            elif kind == "similarity":
                result = JobResult(ok=True, score=0.8)
            else:
                result = JobResult(ok=True, text="犬")

        def write(tx):
            job = tx.get(f"{self.base}/jobs/{payload.job_id}")
            rd = tx.get(self.base)
            private = tx.get(f"{self.base}/private/main")
            if job["revision"] != payload.revision or job["status"] in ("done", "failed"):
                return
            job["status"] = "done" if result.ok else "failed"
            tx.set(f"{self.base}/jobs/{payload.job_id}", job)
            if not result.ok:
                if kind == "gesture_read":
                    rd["gesture_ai_status"] = "failed"
                else:
                    rd["status"] = "failed"
                    room = tx.get(f"rooms/{self.room_id}")
                    room.update(status="failed", fail_reason="ai_failed")
                    tx.set(f"rooms/{self.room_id}", room)
            elif kind == "gesture_read":
                rd["gesture_ai_status"] = "done"
                private["gesture_ai_text"] = result.text
                final = tx.get(f"{self.base}/result/final")
                if final:
                    final["gesture_ai_text"] = result.text
                    tx.set(f"{self.base}/result/final", final)
            elif kind == "similarity":
                rd["result_status"] = "ready"
                tx.set(
                    f"{self.base}/result/final",
                    {
                        "odai": private["odai_text"],
                        "final_image_asset_id": private["outputs"]["4"]["asset_id"],
                        "ai_conclusion": private["outputs"]["5"]["text"],
                        "similarity": result.score,
                        "gesture_ai_text": private.get("gesture_ai_text"),
                    },
                )
            else:
                step = tx.get(f"{self.base}/steps/{index}")
                step["status"] = "done"
                tx.set(f"{self.base}/steps/{index}", step)
                private["outputs"][str(index)] = {"text": result.text, "asset_id": result.asset_id}
                if index == 0:
                    private["odai_text"] = "犬"  # deterministic fixture, not an A-owned odai source
            tx.set(self.base, rd)
            tx.set(f"{self.base}/private/main", private)

        self.store.atomic(write)
        self.game.advance_step(self.room_id, self.round_id)
        return payload

    def to_gesture(self):
        self.start()
        self.complete("image_gen", 0)
        self.post(f"/api/rounds/{self.round_id}/steps/1/submit", body={"text": "犬"}, expected=202)
        session = self.post(f"/api/rounds/{self.round_id}/gesture/start", "b")
        self.session = session["gesture_session_id"]
        return self.session

    def upload(self, *, request_id=None, data=None, mime="video/mp4", expected=200):
        response = self.client.post(
            f"/api/rounds/{self.round_id}/gesture/video",
            headers={"Authorization": "Bearer local:b"},
            data={"gesture_session_id": self.session, "request_id": request_id or str(uuid4())},
            files={"file": ("capture.mp4", data if data is not None else video_bytes(), mime)},
        )
        assert response.status_code == expected, response.text
        return response.json()


def video_bytes(seconds=1, container_format="mp4", *, encoder=None, options=None):
    buffer = BytesIO()
    with av.open(buffer, mode="w", format=container_format, options=options) as container:
        stream = container.add_stream(
            encoder or ("libvpx" if container_format == "webm" else "libx264"), rate=10
        )
        stream.width = stream.height = 32
        stream.pix_fmt = "yuv420p"
        for _ in range(seconds * 10):
            frame = av.VideoFrame(32, 32, "yuv420p")
            for plane in frame.planes:
                plane.update(bytes(plane.buffer_size))
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return buffer.getvalue()


@pytest.fixture
def h():
    harness = Harness()
    yield harness
    harness.client.close()
