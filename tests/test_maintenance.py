import asyncio
import io
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from queue import Queue
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from backend_a.auth import GoogleInternalAuth
from backend_a.errors import ApiError
from backend_a.game import GameService
from backend_a.maintenance import maintenance_once
from backend_a.store import FirestoreStore
from backend_a.worker_bridge import WorkerBridge
from common.storage import AssetStorage
from worker.ai.mock import MockAIClient


@pytest.fixture
def scheduler(h, monkeypatch):
    """Real app verifier, fake Google signature verification; no certificate HTTP."""
    from google.oauth2 import id_token

    def verify(encoded, request, audience):
        assert audience == "https://deadlines.example"
        if encoded != "scheduler":
            raise ValueError("invalid signature, audience, or identity")
        return {"email": "tasks@example.test", "email_verified": True}

    monkeypatch.setattr(id_token, "verify_oauth2_token", verify)
    h.runtime.internal_auth = GoogleInternalAuth("https://deadlines.example", "tasks@example.test")
    with TestClient(
        create_app(h.runtime, internal=True, maintenance_endpoint=True),
        raise_server_exceptions=False,
    ) as client:
        yield client


@pytest.fixture
def second_scheduler(h, scheduler):
    # Separate app and GameService. Emulator stores have separate transaction
    # locks and coordinate through Firestore. Offline uses a shared MemoryStore.
    store = FirestoreStore(h.store.client) if isinstance(h.store, FirestoreStore) else h.store
    assets = AssetStorage(store, h.assets.blobs, h.clock)
    runtime = replace(h.runtime, game=GameService(store, assets, h.tasks, h.settings, h.clock))
    with TestClient(create_app(runtime, internal=True, maintenance_endpoint=True)) as client:
        yield client


def call(client):
    return client.post("/internal/maintenance", headers={"Authorization": "Bearer scheduler"})


def run_concurrently(scheduler, second_scheduler):
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert [
            response.status_code for response in pool.map(call, (scheduler, second_scheduler))
        ] == [
            200,
            200,
        ]


@pytest.mark.parametrize("authorization", [None, "Basic fake", "Bearer ", "Bearer local:a"])
def test_scheduler_rejects_missing_or_client_identity_before_work(
    h, scheduler, monkeypatch, authorization
):
    run = Mock()
    monkeypatch.setattr("api.app.maintenance_once", run)
    response = scheduler.post(
        "/internal/maintenance",
        headers={"Authorization": authorization} if authorization else {},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    run.assert_not_called()


@pytest.mark.parametrize(
    "claims",
    [
        {"email": "other@example.test", "email_verified": True},
        {"email": "tasks@example.test", "email_verified": False},
    ],
)
def test_scheduler_rejects_wrong_or_unverified_sa(scheduler, monkeypatch, claims):
    monkeypatch.setattr("google.oauth2.id_token.verify_oauth2_token", lambda *a, **k: claims)
    run = Mock()
    monkeypatch.setattr("api.app.maintenance_once", run)
    assert call(scheduler).status_code == 401
    run.assert_not_called()


def test_endpoint_is_private_and_only_explicit_deadline_composition(h, scheduler):
    assert h.client.post("/internal/maintenance").status_code == 404
    with TestClient(create_app(h.runtime, internal=True)) as other:
        assert call(other).status_code == 404
    assert scheduler.post("/api/rooms", json={}).status_code == 404
    with pytest.raises(ValueError):
        create_app(h.runtime, maintenance_endpoint=True)


def test_one_request_runs_one_ordered_pass_without_startup_background(h, scheduler, monkeypatch):
    assert scheduler.app.state.maintenance_task is None
    calls = []
    monkeypatch.setattr("backend_a.maintenance.purge_sent_outbox", lambda *a: calls.append("purge"))
    monkeypatch.setattr(
        "backend_a.maintenance.dispatch_outbox", lambda *a: calls.append("dispatch")
    )
    for name in ("recover_job_progress", "recover_job_execution", "cleanup"):
        monkeypatch.setattr(h.game, name, lambda name=name: calls.append(name))
    assert calls == []
    assert call(scheduler).json() == {"accepted": True}
    assert calls == [
        "purge",
        "dispatch",
        "recover_job_progress",
        "recover_job_execution",
        "cleanup",
    ]
    assert call(scheduler).status_code == 200
    assert len(calls) == 10


def test_http_failure_is_retryable_and_does_not_run_later_phases(h, scheduler, monkeypatch):
    original = h.game.recover_job_progress
    monkeypatch.setattr(
        h.game, "recover_job_progress", Mock(side_effect=RuntimeError("store down"))
    )
    cleanup = Mock()
    monkeypatch.setattr(h.game, "cleanup", cleanup)
    response = call(scheduler)
    assert response.status_code == 500
    assert response.json() == {"error": {"code": "INTERNAL", "message": "処理に失敗しました"}}
    cleanup.assert_not_called()
    monkeypatch.setattr(h.game, "recover_job_progress", original)
    assert call(scheduler).status_code == 200
    cleanup.assert_called_once()


def test_public_heartbeats_stay_light_while_periodic_maintenance_retries(h, monkeypatch):
    h.start()
    path = f"/api/rooms/{h.room_id}/heartbeat"
    task_path = "task_outbox/retry-after-maintenance-failure"
    payload = {"target": "worker", "payload": {}, "sent": False}
    h.store.atomic(lambda tx: tx.set(task_path, payload))

    ticks = Queue()

    async def wait_for_tick(seconds):
        assert seconds == 5
        tick = asyncio.Event()
        ticks.put(tick)
        await tick.wait()

    monkeypatch.setattr(
        "api.app.asyncio",
        SimpleNamespace(
            sleep=wait_for_tick,
            create_task=asyncio.create_task,
            CancelledError=asyncio.CancelledError,
        ),
    )
    entered, release = Event(), Event()

    def stalled_pass(game):
        entered.set()
        assert release.wait(15)
        raise RuntimeError("maintenance temporarily unavailable")

    passes = iter((stalled_pass, maintenance_once))
    run = Mock(side_effect=lambda game: next(passes)(game))
    monkeypatch.setattr("api.app.maintenance_once", run)
    with (
        TestClient(create_app(h.runtime)) as client,
        ThreadPoolExecutor(max_workers=3) as pool,
    ):
        try:
            client.portal.call(ticks.get(timeout=5).set)
            assert entered.wait(5)
            assert client.post(path).status_code == 401
            assert (
                client.post(path, headers={"Authorization": "Bearer local:outsider"}).status_code
                == 403
            )

            for _ in range(4):
                h.clock.advance(5)
                beats = [
                    pool.submit(client.post, path, headers={"Authorization": f"Bearer local:{uid}"})
                    for uid in ("a", "b", "c")
                ]
                for uid, beat in zip(("a", "b", "c"), beats, strict=True):
                    response = beat.result(timeout=5)
                    assert response.status_code == 200
                    assert response.json() == {"accepted": True}
                    player = h.store.atomic(
                        lambda tx, uid=uid: tx.get(f"rooms/{h.room_id}/players/{uid}")
                    )
                    assert player["last_seen_at"] == h.clock()

            run.assert_called_once_with(h.game)
            assert not h.store.atomic(lambda tx: tx.get(task_path))["sent"]
        finally:
            release.set()

        client.portal.call(ticks.get(timeout=5).set)
        ticks.get(timeout=5)  # The loop only sleeps again once the retry has finished.
        assert run.call_count == 2
        assert h.store.atomic(lambda tx: tx.get(task_path))["sent"]
        assert "retry-after-maintenance-failure" in h.tasks.messages

    h.game.deadline({"kind": "watchdog", "room_id": h.room_id, "round_id": h.round_id})
    assert h.doc()["status"] == "playing"


def test_two_maintenance_instances_recover_saved_b_result_once(h, scheduler, second_scheduler):
    h.start()
    ai = MockAIClient()
    ai.generate_image = Mock(wraps=ai.generate_image)

    def crash_after_save(*args):
        raise RuntimeError("Worker stopped after write_job_result")

    bridge = WorkerBridge(h.game, ai, advance=crash_after_save)
    payload = h.pending_job("image_gen", 0)
    assert asyncio.run(bridge.handle(payload)) == 500
    assert h.doc(f"/jobs/{payload.job_id}")["advance_pending"]
    saved = h.doc("/private/main")["outputs"]["0"]["asset_id"]
    run_concurrently(scheduler, second_scheduler)
    assert call(scheduler).status_code == 200
    assert h.step(1)["status"] == "active"
    assert not h.doc(f"/jobs/{payload.job_id}")["advance_pending"]
    assert h.doc("/private/main")["outputs"]["0"]["asset_id"] == saved
    ai.generate_image.assert_called_once()
    assert h.store.atomic(lambda tx: tx.list("progress_outbox")) == []


def test_delivery_failure_is_retained_then_recovered(h, scheduler, second_scheduler, monkeypatch):
    h.start()
    payload = {"target": "worker", "payload": {}, "sent": False}
    h.store.atomic(lambda tx: tx.set("task_outbox/maintenance-retry", payload))
    original = h.tasks.send
    monkeypatch.setattr(h.tasks, "send", Mock(side_effect=RuntimeError("queue unavailable")))
    # Existing outbox operations retain per-item failures for the next pass.
    assert call(scheduler).status_code == 200
    assert not h.store.atomic(lambda tx: tx.get("task_outbox/maintenance-retry"))["sent"]
    monkeypatch.setattr(h.tasks, "send", original)
    run_concurrently(scheduler, second_scheduler)
    assert h.store.atomic(lambda tx: tx.get("task_outbox/maintenance-retry"))["sent"]
    assert "maintenance-retry" in h.tasks.messages


def test_scheduler_requeues_abandoned_execution_only_once(h, scheduler, second_scheduler):
    h.start()
    bridge = WorkerBridge(h.game, MockAIClient())
    payload = h.pending_job("image_gen", 0)
    assert bridge._prepare(payload, 0) == ("run", 1)
    h.clock.advance(61)
    run_concurrently(scheduler, second_scheduler)
    assert call(scheduler).status_code == 200
    assert h.doc(f"/jobs/{payload.job_id}")["status"] == "pending"
    recovered = [msg for name, msg in h.tasks.messages.items() if name.startswith("recover-")]
    assert len(recovered) == 1
    assert recovered[0]["payload"] == payload.model_dump(mode="json")


def test_scheduler_recovers_cleanup_without_deleting_generated_images(
    h, scheduler, second_scheduler, monkeypatch
):
    h.to_gesture()
    video = h.upload()["asset_id"]
    image = h.doc("/private/main")["outputs"]["0"]["asset_id"]
    original = h.assets.delete_round_assets
    monkeypatch.setattr(
        h.assets, "delete_round_assets", Mock(side_effect=RuntimeError("storage down"))
    )
    for uid in ("a", "b", "c"):
        h.post(f"/api/rooms/{h.room_id}/leave", uid)
    assert h.store.atomic(lambda tx: tx.list("cleanup_outbox"))
    monkeypatch.setattr(h.assets, "delete_round_assets", original)
    run_concurrently(scheduler, second_scheduler)
    assert call(scheduler).status_code == 200
    assert h.doc(f"/assets/{video}") is None
    assert h.doc(f"/assets/{image}") is not None
    assert h.store.atomic(lambda tx: tx.list("cleanup_outbox")) == []


def test_cloud_runner_uses_150s_and_does_not_forward_keys(h, monkeypatch):
    from backend_a.maintenance_process import run_cloud_maintenance

    h.settings.runtime_mode, h.settings.enable_cloud = "cloud", True
    h.settings.gemini_api_key = "test-key-not-forwarded"
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/must-not-read.json")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-forwarded")
    run = Mock()
    monkeypatch.setattr("backend_a.maintenance_process.subprocess.run", run)
    run_cloud_maintenance(h.settings)
    args, kwargs = run.call_args
    assert args[0] == [sys.executable, "-m", "backend_a.maintenance_worker"]
    assert kwargs["timeout"] == 150 and kwargs["check"] is True
    payload = json.loads(kwargs["input"])
    assert payload["ai_mode"] == "mock"
    assert "gemini_api_key" not in payload
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in kwargs["env"]
    assert "GEMINI_API_KEY" not in kwargs["env"]


def test_timeout_kills_and_reaps_a_real_local_child(h, monkeypatch, tmp_path):
    from backend_a.maintenance_process import run_cloud_maintenance

    h.settings.runtime_mode, h.settings.enable_cloud = "cloud", True
    pidfile = tmp_path / "child.pid"
    script = (
        "import os,time; from pathlib import Path; "
        f"Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(30)"
    )
    actual_run = subprocess.run

    def sleeping_child(command, **kwargs):
        # Test only: replace the cloud worker with a process having no SDKs.
        return actual_run([sys.executable, "-c", script], **kwargs)

    monkeypatch.setattr("backend_a.maintenance_process.MAINTENANCE_TIMEOUT_SECONDS", 2)
    monkeypatch.setattr("backend_a.maintenance_process.subprocess.run", sleeping_child)
    started = time.monotonic()
    with pytest.raises(ApiError) as error:
        run_cloud_maintenance(h.settings)
    assert error.value.status == 500
    assert time.monotonic() - started < 8
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)


@pytest.mark.parametrize(
    "error", [subprocess.CalledProcessError(1, ["test-worker"]), OSError("cannot start child")]
)
def test_child_failure_returns_retryable_http_error(h, monkeypatch, error):
    from backend_a.maintenance_process import run_cloud_maintenance

    h.settings.runtime_mode, h.settings.enable_cloud = "cloud", True
    monkeypatch.setattr("backend_a.maintenance_process.subprocess.run", Mock(side_effect=error))
    with pytest.raises(ApiError) as raised:
        run_cloud_maintenance(h.settings)
    assert raised.value.status == 500 and raised.value.code == "INTERNAL"


def test_cloud_child_entrypoint_builds_one_runtime_and_pass(h, monkeypatch):
    from backend_a import maintenance_worker

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"runtime_mode": "cloud", "enable_cloud": True, "ai_mode": "mock"})),
    )
    build = Mock(return_value=h.runtime)
    run = Mock()
    monkeypatch.setattr(maintenance_worker, "build_runtime", build)
    monkeypatch.setattr(maintenance_worker, "maintenance_once", run)
    maintenance_worker.main()
    build.assert_called_once()
    run.assert_called_once_with(h.game)
    monkeypatch.setattr("sys.stdin", io.StringIO('{"runtime_mode":"local"}'))
    with pytest.raises(ValueError):
        maintenance_worker.main()
    assert build.call_count == 1


def test_cloud_endpoint_rejects_overlap_and_unlocks_after_failure(h, scheduler, monkeypatch):
    h.settings.runtime_mode, h.settings.enable_cloud = "cloud", True
    entered, release = Event(), Event()

    def slow_child(settings):
        entered.set()
        assert release.wait(3)

    monkeypatch.setattr("api.app.run_cloud_maintenance", slow_child)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(call, scheduler)
        try:
            assert entered.wait(2)
            assert call(scheduler).status_code == 500
        finally:
            release.set()
        assert first.result().status_code == 200
    monkeypatch.setattr(
        "api.app.run_cloud_maintenance", Mock(side_effect=ApiError("INTERNAL", 500))
    )
    assert call(scheduler).status_code == 500
    monkeypatch.setattr("api.app.run_cloud_maintenance", Mock())
    assert call(scheduler).status_code == 200
