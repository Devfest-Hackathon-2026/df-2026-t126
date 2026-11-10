import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from api.local import LocalDispatcher, build_local_app
from common.settings import Settings


def test_local_dispatcher_runs_three_player_pipeline_through_b_worker(h):
    queue = LocalDispatcher(h.runtime)
    h.start()
    asyncio.run(queue.tick())
    assert h.step(1)["status"] == "active"
    first = h.doc("/private/main")["outputs"]["0"]["asset_id"]
    asyncio.run(queue.tick())
    assert h.doc("/private/main")["outputs"]["0"]["asset_id"] == first
    h.post(f"/api/rounds/{h.round_id}/steps/1/submit", body={"text": "犬"}, expected=202)
    h.session = h.post(f"/api/rounds/{h.round_id}/gesture/start", "b")["gesture_session_id"]
    h.post(f"/api/rounds/{h.round_id}/gesture/finish", "b", {"gesture_session_id": h.session}, 202)
    asyncio.run(queue.tick())
    assert h.step(3)["status"] == "waiting"
    h.upload()
    assert h.step(3)["status"] == "active"
    h.post(f"/api/rounds/{h.round_id}/steps/3/submit", "c", {"text": "犬"}, 202)
    for _ in range(3):
        asyncio.run(queue.tick())
    assert h.doc()["status"] == "finished"
    for uid in ("a", "b", "c"):
        assert h.get(f"/api/rounds/{h.round_id}/history", uid)["result"]["gesture_ai_text"]


def test_local_dispatcher_does_not_execute_future_deadline(h):
    queue = LocalDispatcher(h.runtime)
    h.start()
    asyncio.run(queue.tick())
    h.clock.advance(4)
    asyncio.run(queue.tick())
    assert h.doc()["status"] == "playing"
    h.clock.advance(11)
    asyncio.run(queue.tick())
    assert h.doc()["status"] == "failed"


def test_local_demo_refuses_cloud_before_runtime_construction(monkeypatch, h):
    monkeypatch.setenv("RUNTIME_MODE", "cloud")
    monkeypatch.setenv("ENABLE_CLOUD", "true")
    monkeypatch.setattr(
        "api.local.build_runtime", lambda _: pytest.fail("must not initialize cloud")
    )
    with pytest.raises(ValueError):
        build_local_app()
    h.runtime.settings = Settings(runtime_mode="cloud", enable_cloud=True)
    with pytest.raises(ValueError):
        LocalDispatcher(h.runtime)


def test_local_app_lifespan_delivers_jobs_without_manual_worker_call(h):
    with TestClient(build_local_app(h.runtime)) as client:
        assert client.get("/health").status_code == 200
        h.start()
        until = time.monotonic() + 10
        while h.step(1)["status"] != "active" and time.monotonic() < until:
            time.sleep(0.02)
        assert h.step(1)["status"] == "active"
        assert client.post("/tasks/run", json={}).status_code == 404
