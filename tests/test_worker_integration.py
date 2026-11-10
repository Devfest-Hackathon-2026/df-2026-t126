"""Use B's real handler/jobs/MockAIClient, never Harness.complete()."""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from backend_a import progress
from backend_a.maintenance import maintenance_once
from backend_a.worker_bridge import GameJobIO, GameJobSink, WorkerBridge
from common.enums import ErrorCode
from common.models import JobResult
from worker.ai.base import AIError
from worker.ai.mock import MockAIClient
from worker.jobs import run_job


class ObservedAI(MockAIClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.images = self.reads = self.conclusions = self.embeddings = 0
        self.prompts = []
        self.batches = []

    async def generate_image(self, prompt):
        self.images += 1
        self.prompts.append(prompt)
        return await super().generate_image(prompt)

    async def read_gesture(self, batches):
        self.reads += 1
        self.batches = batches
        return await super().read_gesture(batches)

    async def conclude(self, image):
        self.conclusions += 1
        assert image.startswith(b"\x89PNG\r\n\x1a\n")
        return await super().conclude(image)

    async def embed(self, text):
        self.embeddings += 1
        return await super().embed(text)


@pytest.fixture
def bridge(h):
    progress.configure_progress(h.game)
    return WorkerBridge(h.game, ObservedAI(), advance=progress.advance_step)


def deliver(h, bridge, kind, index=None, *, payload=None, retry_count=0):
    p = payload or h.pending_job(kind, index)
    assert asyncio.run(bridge.handle(p, retry_count=retry_count)) == 200
    return p


def to_gesture(h, bridge):
    h.start()
    deliver(h, bridge, "image_gen", 0)
    h.post(f"/api/rounds/{h.round_id}/steps/1/submit", body={"text": "犬が走る"}, expected=202)
    h.session = h.post(f"/api/rounds/{h.round_id}/gesture/start", "b")["gesture_session_id"]


def finish_gesture(h):
    h.post(f"/api/rounds/{h.round_id}/gesture/finish", "b", {"gesture_session_id": h.session}, 202)


def finish_main(h, bridge):
    h.post(f"/api/rounds/{h.round_id}/steps/3/submit", "c", {"text": "犬"}, 202)
    deliver(h, bridge, "image_gen", 4)
    deliver(h, bridge, "conclude", 5)
    deliver(h, bridge, "similarity")


@pytest.mark.parametrize("countdown,record", [(0, 5), (3, 5), (7, 5), (None, 8)])
def test_my_input_gesture_timing_uses_round_start_snapshot(h, bridge, countdown, record):
    config = {"text_seconds": 60}
    if countdown is None:
        countdown = 15  # No stored timing: exercise the product defaults.
    else:
        config.update(countdown_seconds=countdown, record_seconds=record)
    h.store.atomic(lambda tx: tx.set("config/game", config))
    h.start()
    deliver(h, bridge, "image_gen", 0)
    a_input = h.get(f"/api/rounds/{h.round_id}/my-input", "a")
    assert "countdown_seconds" not in a_input and "record_seconds" not in a_input
    h.store.atomic(
        lambda tx: tx.set("config/game", {**config, "countdown_seconds": 20, "record_seconds": 10})
    )
    h.post(f"/api/rounds/{h.round_id}/steps/1/submit", body={"text": "犬"}, expected=202)
    path = f"/api/rounds/{h.round_id}/my-input"
    b_input = h.get(path, "b")
    assert b_input["type"] == "gesture" and b_input["input"] == {"kind": "text", "text": "犬"}
    assert b_input["countdown_seconds"] == countdown and b_input["record_seconds"] == record
    h.get(path, "a", expected=403)
    h.get(path, "c", expected=403)
    h.get(path, "outsider", expected=403)
    h.session = h.post(f"/api/rounds/{h.round_id}/gesture/start", "b")["gesture_session_id"]
    assert h.get(path, "b") == b_input
    h.upload()
    finish_gesture(h)
    c_input = h.get(path, "c")
    assert "countdown_seconds" not in c_input and "record_seconds" not in c_input


@pytest.mark.parametrize("blob_backend", ["memory", "emulator"])
def test_real_b_pipeline_completes_three_player_game(h, bridge, blob_backend, monkeypatch):
    if blob_backend == "emulator":
        if os.environ.get("RUN_FIRESTORE_EMULATOR_TESTS") != "1":
            pytest.skip("Requires local Storage emulator")
        from google.auth.credentials import AnonymousCredentials
        from google.cloud import storage

        from backend_a.runtime import localhost_endpoint
        from common.storage import GoogleBlobs

        host = os.environ.get("FIREBASE_STORAGE_EMULATOR_HOST", "")
        localhost_endpoint(host)
        monkeypatch.setenv("STORAGE_EMULATOR_HOST", f"http://{host}")
        client = storage.Client(
            project="demo-gesture-relay",
            credentials=AnonymousCredentials(),
            client_options={"api_endpoint": f"http://{host}"},
        )
        h.assets.blobs = GoogleBlobs(client.bucket("demo-gesture-relay.appspot.com"))
        # Exercise the actual deployment composition with independent SDK clients.
        from backend_a.runtime import build_runtime
        from common.settings import Settings

        worker_runtime = build_runtime(Settings(runtime_mode="emulator"))
        worker_game = worker_runtime.game
        worker_game.clock = h.clock
        worker_game.storage.clock = h.clock
        bridge.game = worker_game
        progress.configure_progress(worker_game)
    to_gesture(h, bridge)
    assert h.doc("/private/main")["odai_text"]  # B's actual FileOdaiSource
    response = h.client.post(
        f"/api/rounds/{h.round_id}/gesture/batches",
        headers={"Authorization": "Bearer local:b"},
        json={
            "gesture_session_id": h.session,
            "sequence_number": 4,
            "mirrored": True,
            "samples": [{"timestamp_ms": 100, "hands": []}],
        },
    )
    assert response.status_code == 202
    finish_gesture(h)
    deliver(h, bridge, "gesture_read", 2)
    assert h.step(3)["status"] == "waiting"
    assert bridge.ai.batches[0].sequence_number == 4
    video = h.upload()["asset_id"]
    assert h.get(f"/api/rounds/{h.round_id}/my-input", "c")["input"]["asset_id"] == video
    finish_main(h, bridge)
    history = h.get(f"/api/rounds/{h.round_id}/history", "c")
    assert history["round_status"] == "finished"
    assert history["result"]["gesture_ai_text"] == bridge.ai.gesture_text
    assert history["result"]["ai_conclusion"] == bridge.ai.conclusion
    assert bridge.ai.images == 2 and bridge.ai.conclusions == 1 and bridge.ai.embeddings == 2
    jobs = h.store.atomic(lambda tx: tx.list(h.base + "/jobs"))
    assert len(jobs) == 5 and all(job["status"] == "done" for _, job in jobs)
    assert all(not job["advance_pending"] for _, job in jobs)
    assert (
        h.doc("/assets/" + history["result"]["final_image_asset_id"])["content_type"] == "image/png"
    )


@pytest.mark.parametrize("kind,index", [("image_gen", 0), ("gesture_read", 2)])
def test_real_worker_retry_exhaustion_is_fatal_only_for_main(h, bridge, kind, index):
    if kind == "gesture_read":
        to_gesture(h, bridge)
        h.upload()
        finish_gesture(h)
    else:
        h.start()

    class FailingAI(ObservedAI):
        async def generate_image(self, prompt):
            raise AIError(ErrorCode.ai_timeout, "一時的な失敗", True)

        async def read_gesture(self, batches):
            raise AIError(ErrorCode.ai_timeout, "一時的な失敗", True)

    bridge.ai = FailingAI()
    p = h.pending_job(kind, index)
    assert asyncio.run(bridge.handle(p)) == 500
    assert asyncio.run(bridge.handle(p, retry_count=1)) == 500
    assert asyncio.run(bridge.handle(p, retry_count=2)) == 200
    assert h.doc(f"/jobs/{p.job_id}")["attempt"] == 3
    assert h.doc(f"/jobs/{p.job_id}")["status"] == "failed"
    if kind == "gesture_read":
        assert h.doc()["status"] == "playing"
        assert h.step(3)["status"] == "active"
        assert h.doc()["gesture_ai_status"] == "failed"
        bridge.ai = ObservedAI()
        finish_main(h, bridge)
        assert h.doc()["status"] == "finished"
    else:
        assert h.doc()["status"] == "failed"
        assert h.step(0)["status"] == "failed"
        room = h.store.atomic(lambda tx: tx.get(f"rooms/{h.room_id}"))
        assert room["fail_reason"] == "ai_failed"
        assert h.get(f"/api/rounds/{h.round_id}/history", "c")["round_status"] == "failed"


def test_duplicate_delivery_reuses_committed_result_without_ai_or_revision_change(h, bridge):
    h.start()
    p = deliver(h, bridge, "image_gen", 0)
    before, private = h.doc(), h.doc("/private/main")
    assert asyncio.run(bridge.handle(p, retry_count=20)) == 200
    assert h.doc() == before and h.doc("/private/main") == private
    assert bridge.ai.images == 1
    assert len(h.store.atomic(lambda tx: tx.list(h.base + "/assets"))) == 1


@pytest.mark.parametrize("crash_after_advance", [False, True])
def test_saved_result_recovers_without_reinference_after_progress_failure(
    h, bridge, crash_after_advance
):
    h.start()
    p = h.pending_job("image_gen", 0)
    original = bridge.advance

    def fail(room, rd):
        if crash_after_advance:
            original(room, rd)
        raise RuntimeError("Worker stopped before progress acknowledgement")

    bridge.advance = fail
    assert asyncio.run(bridge.handle(p)) == 500
    job = h.doc(f"/jobs/{p.job_id}")
    assert job["status"] == "done" and job["advance_pending"]
    saved = h.doc("/private/main")["outputs"]["0"]["asset_id"]
    bridge.advance = original
    assert asyncio.run(bridge.handle(p, retry_count=1)) == 200
    assert h.step(1)["status"] == "active"
    assert not h.doc(f"/jobs/{p.job_id}")["advance_pending"]
    assert bridge.ai.images == 1
    assert h.doc("/private/main")["outputs"]["0"]["asset_id"] == saved


def test_stale_payload_or_result_cannot_replace_outputs(h, bridge):
    h.start()
    p = h.pending_job("image_gen", 0)
    stale = p.model_copy(update={"revision": p.revision + 10})
    assert asyncio.run(bridge.handle(stale)) == 200
    assert bridge.ai.images == 0
    deliver(h, bridge, "image_gen", 0, payload=p)
    before, private = h.doc(), h.doc("/private/main")
    sink = GameJobSink(h.game, stale, 1, h.game.advance_step)
    asyncio.run(sink.write_job_result(stale, JobResult(ok=True, asset_id="f" * 32), final=True))
    asyncio.run(sink.advance_step(h.room_id, h.round_id))
    assert h.doc() == before and h.doc("/private/main") == private


def test_revision_changes_during_inference_discard_result_and_generated_asset(h, bridge):
    h.start()

    class ChangedRevision(ObservedAI):
        async def generate_image(self, prompt):
            def invalidate(tx):
                rd = tx.get(h.base)
                rd["revision"] += 1
                tx.set(h.base, rd)

            h.store.atomic(invalidate)
            return await super().generate_image(prompt)

    bridge.ai = ChangedRevision()
    p = h.pending_job("image_gen", 0)
    assert asyncio.run(bridge.handle(p)) == 200
    assert h.doc("/private/main")["outputs"] == {}
    assert h.step(1)["status"] == "waiting"
    assert h.store.atomic(lambda tx: tx.list(h.base + "/assets")) == []


def test_late_gesture_result_after_game_finished_updates_result_only(h, bridge):
    to_gesture(h, bridge)
    h.upload()
    finish_gesture(h)
    gesture = h.pending_job("gesture_read", 2)
    finish_main(h, bridge)
    before = h.doc()
    assert h.doc("/result/final")["gesture_ai_text"] is None
    deliver(h, bridge, "gesture_read", 2, payload=gesture)
    after = h.doc()
    assert after["status"] == "finished"
    assert after["revision"] == before["revision"]
    assert after["current_step_index"] == before["current_step_index"]
    assert h.doc("/result/final")["gesture_ai_text"] == bridge.ai.gesture_text


def test_image_lifecycle_deletion_keeps_history_and_returns_asset_not_found(h, bridge):
    to_gesture(h, bridge)
    h.upload()
    finish_gesture(h)
    finish_main(h, bridge)
    path = f"/api/rounds/{h.round_id}"
    history = h.get(path + "/history", "c")
    image = history["result"]["final_image_asset_id"]
    doc = h.doc(f"/assets/{image}")
    h.clock.advance(24 * 3600)
    # The Emulator does not run GCS lifecycle rules: simulate the external deletion.
    h.assets.blobs.delete(doc["path"])
    response = h.get(f"{path}/assets/{image}", "c", expected=404)
    assert response["error"]["code"] == "ASSET_NOT_FOUND"
    assert h.get(path + "/history", "c") == history
    assert h.doc(f"/assets/{image}") == doc
    assert h.doc()["status"] == "finished"
    h.get(f"{path}/assets/{image}", "outsider", expected=403)
    h.post(f"/api/rooms/{h.room_id}/leave", "c")
    h.get(f"{path}/assets/{image}", "c", expected=403)


def test_nonretryable_safety_failure_commits_once(h, bridge):
    h.start()

    class BlockedAI(ObservedAI):
        async def generate_image(self, prompt):
            raise AIError(ErrorCode.ai_blocked, "生成を拒否しました", False)

    bridge.ai = BlockedAI()
    p = deliver(h, bridge, "image_gen", 0)
    assert h.doc(f"/jobs/{p.job_id}")["attempt"] == 1
    assert h.doc()["status"] == "failed"
    assert asyncio.run(bridge.handle(p)) == 200


def test_actual_run_job_reads_last_image_and_text_from_a_store(h, bridge):
    to_gesture(h, bridge)
    h.upload()
    finish_gesture(h)
    h.post(f"/api/rounds/{h.round_id}/steps/3/submit", "c", {"text": "   "}, 202)
    deliver(h, bridge, "image_gen", 4)
    from worker.prompts import PROMPTS

    assert bridge.ai.prompts[-1] == PROMPTS.image_from_empty
    p = h.pending_job("conclude", 5)
    result = asyncio.run(run_job(p, ai=bridge.ai, io=GameJobIO(h.game)))
    assert result.ok and result.text == bridge.ai.conclusion


def test_concurrent_duplicate_does_not_run_a_second_inference(h, bridge):
    h.start()
    p = h.pending_job("image_gen", 0)
    ready, finish = Barrier(2), Barrier(2)

    class WaitingAI(ObservedAI):
        async def generate_image(self, prompt):
            ready.wait(timeout=10)
            finish.wait(timeout=10)
            return await super().generate_image(prompt)

    bridge.ai = WaitingAI()
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(lambda: asyncio.run(bridge.handle(p)))
        ready.wait(timeout=10)
        assert asyncio.run(bridge.handle(p)) == 500
        finish.wait(timeout=10)
        assert first.result(timeout=10) == 200
    assert bridge.ai.images == 1
    assert h.doc(f"/jobs/{p.job_id}")["attempt"] == 1


def test_recorded_result_contains_server_timestamp_and_private_data_only(h, bridge):
    h.start()
    p = deliver(h, bridge, "image_gen", 0)
    job = h.doc(f"/jobs/{p.job_id}")
    assert job["finalized_at"] == h.clock()
    assert job["result"]["asset_id"] == h.doc("/private/main")["outputs"]["0"]["asset_id"]
    assert "asset_id" not in h.step(0) and "text" not in h.step(0)


def test_missing_or_wrong_job_is_acknowledged_without_side_effects(h, bridge):
    h.start()
    p = h.pending_job("image_gen", 0)
    unknown = p.model_copy(update={"job_id": "unknown"})
    before = h.doc()
    assert asyncio.run(bridge.handle(unknown)) == 200
    assert h.doc() == before and bridge.ai.images == 0
    with pytest.raises(ValueError):
        asyncio.run(bridge.handle(p.model_copy(update={"room_id": "../unsafe"})))


@pytest.mark.parametrize("kind,index", [("image_gen", 4), ("conclude", 5), ("similarity", None)])
def test_later_result_checkpoints_recover_game_without_duplicate_ai(h, bridge, kind, index):
    to_gesture(h, bridge)
    h.upload()
    finish_gesture(h)
    h.post(f"/api/rounds/{h.round_id}/steps/3/submit", "c", {"text": "犬"}, 202)
    if kind in ("conclude", "similarity"):
        deliver(h, bridge, "image_gen", 4)
    if kind == "similarity":
        deliver(h, bridge, "conclude", 5)
    p = h.pending_job(kind, index)
    advance = bridge.advance

    def crash(*args):
        raise RuntimeError("stopped after successful result write")

    bridge.advance = crash
    assert asyncio.run(bridge.handle(p)) == 500
    before = (bridge.ai.images, bridge.ai.conclusions, bridge.ai.embeddings)
    assert h.doc(f"/jobs/{p.job_id}")["advance_pending"]
    bridge.advance = advance
    assert asyncio.run(bridge.handle(p, retry_count=1)) == 200
    assert (bridge.ai.images, bridge.ai.conclusions, bridge.ai.embeddings) == before
    assert not h.doc(f"/jobs/{p.job_id}")["advance_pending"]
    if kind == "similarity":
        assert h.doc()["status"] == "finished"


def test_result_transaction_failure_retries_and_discards_uncommitted_image(h, bridge, monkeypatch):
    h.start()
    p = h.pending_job("image_gen", 0)
    original = GameJobSink.write_job_result

    async def broken(*args, **kwargs):
        raise RuntimeError("result transaction unavailable")

    monkeypatch.setattr(GameJobSink, "write_job_result", broken)
    assert asyncio.run(bridge.handle(p)) == 500
    assert h.doc("/private/main")["outputs"] == {}
    assert h.store.atomic(lambda tx: tx.list(h.base + "/assets")) == []
    monkeypatch.setattr(GameJobSink, "write_job_result", original)
    deliver(h, bridge, "image_gen", 0, payload=p, retry_count=1)
    assert h.step(1)["status"] == "active" and bridge.ai.images == 2


def test_late_background_success_during_c_turn_preserves_c_deadline(h, bridge):
    to_gesture(h, bridge)
    h.upload()
    finish_gesture(h)
    before = h.step(3)
    deliver(h, bridge, "gesture_read", 2)
    assert h.step(3) == before
    assert h.doc()["current_step_index"] == 3


def test_late_background_after_everyone_returns_is_ignored(h, bridge):
    to_gesture(h, bridge)
    h.upload()
    finish_gesture(h)
    p = h.pending_job("gesture_read", 2)
    for uid in ("a", "b", "c"):
        h.post(f"/api/rooms/{h.room_id}/leave", uid)
    before = h.doc("/private/main")
    deliver(h, bridge, "gesture_read", 2, payload=p)
    assert h.doc("/private/main") == before and bridge.ai.reads == 0


def test_invalid_ai_text_is_retried_then_fails_without_stalling_main(h, bridge):
    to_gesture(h, bridge)
    h.upload()
    finish_gesture(h)
    bridge.ai.gesture_text = "   "
    p = h.pending_job("gesture_read", 2)
    assert asyncio.run(bridge.handle(p)) == 500
    assert asyncio.run(bridge.handle(p, retry_count=1)) == 500
    assert asyncio.run(bridge.handle(p, retry_count=2)) == 200
    assert h.doc()["gesture_ai_status"] == "failed"
    assert h.doc()["status"] == "playing" and h.step(3)["status"] == "active"


def test_inference_timeout_uses_bounded_persisted_attempts(h, bridge):
    h.start()
    p = h.pending_job("image_gen", 0)

    class HungAI(ObservedAI):
        async def generate_image(self, prompt):
            await asyncio.sleep(60)

    bridge.ai = HungAI()
    h.settings.ai_timeout_s = 0.01
    assert asyncio.run(bridge.handle(p)) == 500
    assert asyncio.run(bridge.handle(p, retry_count=1)) == 500
    assert asyncio.run(bridge.handle(p, retry_count=2)) == 200
    assert asyncio.run(bridge.handle(p, retry_count=3)) == 200
    assert h.doc(f"/jobs/{p.job_id}")["attempt"] == 3
    assert h.doc()["status"] == "failed"


def test_private_worker_http_maps_retry_count_and_authenticates_tasks(h, bridge):
    from fastapi.testclient import TestClient

    from api.worker_app import create_worker_app
    from backend_a.errors import ApiError

    class TaskIdentity:
        def verify(self, token):
            if token != "test-task-identity":
                raise ApiError("UNAUTHENTICATED", 401)

    h.runtime.internal_auth = TaskIdentity()
    app = create_worker_app(h.runtime, bridge.ai)
    h.start()
    p = h.pending_job("image_gen", 0)
    body = p.model_dump(mode="json")
    with TestClient(app) as client:
        assert client.post("/tasks/run", json=body).status_code == 401
        headers = {"Authorization": "Bearer test-task-identity"}
        assert client.post("/tasks/run", json=body, headers=headers).status_code == 200
        assert h.step(1)["status"] == "active"
        assert client.post("/internal/jobs", json=body, headers=headers).status_code == 200
        assert bridge.ai.images == 1
        assert (
            client.post(
                "/tasks/run", json=body, headers={**headers, "X-CloudTasks-TaskRetryCount": "-1"}
            ).status_code
            == 400
        )
    assert h.client.post("/tasks/run", json=body).status_code == 404


def test_text_submit_racing_timeout_commits_exactly_one_outcome(h, bridge):
    from uuid import uuid4

    h.start()
    deliver(h, bridge, "image_gen", 0)
    revision = h.doc()["revision"]
    h.clock.advance(65)
    h.post(f"/api/rooms/{h.room_id}/heartbeat", "a")
    barrier = Barrier(2)

    def submit():
        barrier.wait(timeout=10)
        return h.client.post(
            f"/api/rounds/{h.round_id}/steps/1/submit",
            headers={"Authorization": "Bearer local:a"},
            json={"request_id": str(uuid4()), "text": "boundary"},
        ).status_code

    def expire():
        barrier.wait(timeout=10)
        h.game.deadline(
            {
                "room_id": h.room_id,
                "round_id": h.round_id,
                "kind": "step",
                "step_index": 1,
                "revision": revision,
            }
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        submitted, expired = pool.submit(submit), pool.submit(expire)
        status = submitted.result(timeout=20)
        expired.result(timeout=20)
    assert status in (202, 409)
    if status == 202:
        assert h.doc()["status"] == "playing" and h.step(2)["status"] == "active"
        assert h.doc("/private/main")["outputs"]["1"]["text"] == "boundary"
    else:
        assert h.doc()["status"] == "failed" and h.step(2)["status"] == "waiting"
        assert "1" not in h.doc("/private/main")["outputs"]


def test_maintenance_recovers_last_ai_attempt_without_task_redelivery(h, bridge):
    h.start()
    p = h.pending_job("image_gen", 0)

    def fail(*args):
        raise RuntimeError("progress unavailable on final AI delivery")

    bridge.advance = fail
    assert asyncio.run(bridge.handle(p, retry_count=2)) == 500
    assert h.doc(f"/jobs/{p.job_id}")["attempt"] == 3
    assert h.doc(f"/jobs/{p.job_id}")["status"] == "done"
    assert h.store.atomic(lambda tx: tx.list("progress_outbox"))
    # No fourth handle_job call: A's maintenance drains the durable checkpoint.
    maintenance_once(h.game)
    assert h.step(1)["status"] == "active"
    assert bridge.ai.images == 1
    assert not h.doc(f"/jobs/{p.job_id}")["advance_pending"]
    assert h.store.atomic(lambda tx: tx.list("progress_outbox")) == []


def test_progress_reconciler_failure_remains_durable_and_idempotent(h, bridge, monkeypatch):
    h.start()
    p = h.pending_job("image_gen", 0)

    def fail(*args):
        raise RuntimeError("progress transaction failed")

    bridge.advance = fail
    assert asyncio.run(bridge.handle(p)) == 500
    original = h.game.advance_step
    monkeypatch.setattr(h.game, "advance_step", fail)
    h.game.recover_job_progress()
    assert h.store.atomic(lambda tx: tx.list("progress_outbox"))
    monkeypatch.setattr(h.game, "advance_step", original)
    h.game.recover_job_progress()
    snapshot = h.doc()
    h.game.recover_job_progress()
    assert h.doc() == snapshot and h.step(1)["status"] == "active"


def test_interrupted_inference_can_be_reclaimed_on_cloud_retry(h, bridge):
    h.start()
    p = h.pending_job("image_gen", 0)
    assert bridge._prepare(p, 0) == ("run", 1)  # simulate death before result commit
    deliver(h, bridge, "image_gen", 0, payload=p, retry_count=1)
    assert h.step(1)["status"] == "active"
    assert h.doc(f"/jobs/{p.job_id}")["attempt"] == 2


@pytest.mark.parametrize("old_fails", [False, True])
def test_old_attempt_cannot_commit_or_retry_after_new_attempt_starts(h, old_fails):
    h.start()
    payload = h.pending_job("image_gen", 0)

    async def run():
        old_started, new_started = asyncio.Event(), asyncio.Event()
        finish_old, finish_new = asyncio.Event(), asyncio.Event()

        class OldAI(MockAIClient):
            async def generate_image(self, prompt):
                old_started.set()
                await finish_old.wait()
                if old_fails:
                    raise AIError(ErrorCode.ai_failed, "old attempt failed", True)
                return await super().generate_image(prompt)

        class NewAI(MockAIClient):
            async def generate_image(self, prompt):
                new_started.set()
                await finish_new.wait()
                return await super().generate_image(prompt)

        old = asyncio.create_task(WorkerBridge(h.game, OldAI()).handle(payload))
        await asyncio.wait_for(old_started.wait(), 5)
        new = asyncio.create_task(WorkerBridge(h.game, NewAI()).handle(payload, retry_count=1))
        await asyncio.wait_for(new_started.wait(), 5)
        finish_old.set()
        assert await old == (500 if old_fails else 200)
        job = h.doc(f"/jobs/{payload.job_id}")
        assert (job["attempt"], job["status"]) == (2, "processing")
        assert not h.assets.blobs.objects
        assert not h.store.atomic(lambda tx: tx.list(f"{h.base}/assets"))

        finish_new.set()
        assert await new == 200
        job = h.doc(f"/jobs/{payload.job_id}")
        assert (job["attempt"], job["status"]) == (2, "done")
        assert len(h.assets.blobs.objects) == 1
        assert h.step(1)["status"] == "active"

    asyncio.run(run())


def test_unpublished_asset_is_never_history_even_when_its_step_is_visible(h, bridge):
    h.start()
    deliver(h, bridge, "image_gen", 0)
    orphan = h.assets.save_asset(
        h.room_id, h.round_id, "image", 0, b"uncommitted-fixture", "image/png"
    )
    h.get(f"/api/rounds/{h.round_id}/assets/{orphan}", "a", expected=403)
    h.post(f"/api/rounds/{h.round_id}/steps/1/submit", body={"text": "犬"}, expected=202)
    assert not h.game.can_read_asset("a", h.round_id, orphan)
    first = h.doc("/private/main")["outputs"]["0"]["asset_id"]
    assert h.game.can_read_asset("a", h.round_id, first)


@pytest.mark.parametrize("kind,index", [("image_gen", 0), ("gesture_read", 2)])
def test_abandoned_final_inference_is_finalized_without_a_fourth_delivery(h, bridge, kind, index):
    if kind == "gesture_read":
        to_gesture(h, bridge)
        h.upload()
        finish_gesture(h)
    else:
        h.start()
    p = h.pending_job(kind, index)
    assert bridge._prepare(p, 2) == ("run", 3)  # last receipt died before result persistence
    h.clock.advance(61)
    h.game.recover_job_execution()
    job = h.doc(f"/jobs/{p.job_id}")
    assert job["status"] == "failed" and job["attempt"] == 3
    assert h.doc()["status"] == ("playing" if kind == "gesture_read" else "failed")
    if kind == "gesture_read":
        assert h.step(3)["status"] == "active" and h.doc()["gesture_ai_status"] == "failed"
    assert h.store.atomic(lambda tx: tx.list("execution_outbox")) == []


def test_lost_inference_receipt_requeues_with_new_task_name(h, bridge):
    h.start()
    p = h.pending_job("image_gen", 0)
    assert bridge._prepare(p, 0) == ("run", 1)
    h.clock.advance(61)
    h.game.recover_job_execution()
    assert h.doc(f"/jobs/{p.job_id}")["status"] == "pending"
    recovered = [msg for name, msg in h.tasks.messages.items() if name.startswith("recover-")]
    assert len(recovered) == 1 and recovered[0]["payload"] == p.model_dump(mode="json")
    deliver(h, bridge, "image_gen", 0, payload=p)
    assert h.doc(f"/jobs/{p.job_id}")["attempt"] == 2
    assert h.step(1)["status"] == "active"
