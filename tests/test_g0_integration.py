"""G0 boundary checks against B's latest retry/fallback/preprocessing code."""

import asyncio
import json
from types import SimpleNamespace

from backend_a.worker_bridge import GameJobIO, WorkerBridge
from common.settings import Settings
from tests.test_worker_integration import ObservedAI, deliver, finish_gesture, to_gesture
from worker.ai.real import RealAIClient


def test_a_batches_are_numeric_ordered_deduplicated_then_preprocessed_by_b(h):
    bridge = WorkerBridge(h.game, ObservedAI())
    to_gesture(h, bridge)

    def send(seq, timestamp):
        response = h.client.post(
            f"/api/rounds/{h.round_id}/gesture/batches",
            headers={"Authorization": "Bearer local:b"},
            json={
                "gesture_session_id": h.session,
                "sequence_number": seq,
                "mirrored": True,
                "samples": [{"timestamp_ms": timestamp, "hands": []}],
            },
        )
        assert response.status_code == 202

    send(10, 100)
    send(2, 20)
    send(10, 999)  # same sequence: preserve the first accepted body
    finish_gesture(h)
    payload = h.pending_job("gesture_read", 2)
    batches = asyncio.run(GameJobIO(h.game).load_batches(payload))
    assert [b.sequence_number for b in batches] == [2, 10]
    assert [b.samples[0].timestamp_ms for b in batches] == [20, 100]

    captured = {}

    async def fake_content(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(text="犬")

    # Mock transport only: run B's real preprocessing and actual handler/jobs.
    ai = RealAIClient(Settings(ai_mode="mock"))
    ai._clients["vertex:global"] = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=fake_content))
    )
    bridge.ai = ai
    deliver(h, bridge, "gesture_read", 2, payload=payload)
    prepared = json.loads(captured["contents"].rsplit("\n\n", 1)[1])
    assert prepared["total_samples"] == 2 and prepared["mirrored"] is True
    assert [s["t"] for s in prepared["samples"]] == [20, 100]
    assert h.doc("/private/main")["gesture_ai_text"] == "犬"
    assert h.step(3)["status"] == "waiting"  # no recording saved yet


def test_b_429_retry_and_provider_fallback_persist_one_a_job(h, monkeypatch):
    from google.genai import errors

    h.start()
    delays, calls = [], []

    async def fake_sleep(delay):
        delays.append(delay)

    async def vertex(**kwargs):
        calls.append("vertex")
        raise errors.APIError(
            429, {"error": {"message": "mock rate limit", "status": "RESOURCE_EXHAUSTED"}}
        )

    async def developer(**kwargs):
        calls.append("developer")
        # Use the existing B mock PNG; no real SDK client or credentials.
        from worker.ai.mock import MockAIClient

        image = await MockAIClient().generate_image("fixture")
        return SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    finish_reason=None,
                    content=SimpleNamespace(
                        parts=[SimpleNamespace(inline_data=SimpleNamespace(data=image))]
                    ),
                )
            ]
        )

    monkeypatch.setattr("worker.ai.real.asyncio.sleep", fake_sleep)
    ai = RealAIClient(Settings(ai_mode="mock", gemini_api_key="mock-key-never-used"))
    for provider, fake in (("vertex", vertex), ("developer", developer)):
        ai._clients[f"{provider}:global" if provider == "vertex" else provider] = SimpleNamespace(
            aio=SimpleNamespace(models=SimpleNamespace(generate_content=fake))
        )
    bridge = WorkerBridge(h.game, ai)
    payload = h.pending_job("image_gen", 0)
    assert asyncio.run(bridge.handle(payload)) == 200
    assert calls == ["vertex", "vertex", "vertex", "developer"]
    assert len(delays) == 2 and 4.8 <= delays[0] <= 7.2 and 9.6 <= delays[1] <= 14.4
    job = h.doc(f"/jobs/{payload.job_id}")
    assert job["status"] == "done" and job["attempt"] == 1
    assert h.step(1)["status"] == "active"
    assert asyncio.run(bridge.handle(payload, retry_count=1)) == 200
    assert len(calls) == 4  # no second inference after the result committed
