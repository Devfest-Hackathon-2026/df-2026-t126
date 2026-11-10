from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend_a.errors import ApiError
from backend_a.runtime import build_runtime
from common.models import JobResult
from common.settings import Settings
from common.storage import AssetStorage


def test_watchdog_redelivery_creates_only_one_successor(h):
    h.start()
    watchdog = next(
        msg["payload"]
        for msg in h.tasks.messages.values()
        if msg["payload"].get("kind") == "watchdog"
    )
    h.clock.advance(5)
    for uid in ("a", "b", "c"):
        h.post(f"/api/rooms/{h.room_id}/heartbeat", uid)
    h.game.deadline(watchdog)
    after = len(h.tasks.messages)
    h.clock.advance(1)
    h.game.deadline(watchdog)
    assert len(h.tasks.messages) == after


def test_cloud_runtime_rejects_inherited_unsigned_auth_emulator(monkeypatch):
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099")
    with pytest.raises(ValueError, match="must not inherit"):
        build_runtime(Settings(runtime_mode="cloud", enable_cloud=True))


def test_auto_flag_cannot_change_server_deadline(h):
    h.start()
    h.complete("image_gen", 0)
    deadline = h.step(1)["deadline_at"]
    h.post(
        f"/api/rounds/{h.round_id}/steps/1/submit", body={"text": "", "is_auto": True}, expected=202
    )
    assert h.step(1)["deadline_at"] == deadline
    assert not h.step(1)["timed_out"]
    assert h.step(1)["is_auto"]


def test_role_unlock_and_start_requires_all_roles(h):
    h.lobby()
    h.post(f"/api/rooms/{h.room_id}/role", "c", {"role": None})
    response = h.post(f"/api/rooms/{h.room_id}/start", expected=409)
    assert response["error"]["code"] == "ROLES_NOT_READY"
    h.post(f"/api/rooms/{h.room_id}/role", "c", {"role": "C"})
    h.start()


def test_join_code_rate_limit_survives_failed_requests(h):
    h.settings.join_attempt_limit = 2
    h.post("/api/rooms/join", "bad", {"name": "bad", "consented": True, "join_code": "0000"}, 404)
    h.post("/api/rooms/join", "bad", {"name": "bad", "consented": True, "join_code": "0000"}, 404)
    h.post("/api/rooms/join", "bad", {"name": "bad", "consented": True, "join_code": "0000"}, 429)
    h.clock.advance(61)
    h.post("/api/rooms/join", "bad", {"name": "bad", "consented": True, "join_code": "0000"}, 404)


def test_failed_video_storage_never_activates_c_or_leaves_asset_doc(h, monkeypatch):
    h.to_gesture()
    h.post(f"/api/rounds/{h.round_id}/gesture/finish", "b", {"gesture_session_id": h.session}, 202)

    def fail(*args):
        raise RuntimeError("disk failed")

    monkeypatch.setattr(h.assets.blobs, "put", fail)
    response = h.upload(expected=500)
    assert response["error"]["code"] == "INTERNAL"
    assert h.step(3)["status"] == "waiting"
    assert h.doc("/private/main")["gesture"]["video_asset_id"] is None


def test_metadata_failure_compensates_blob_write(h, monkeypatch):
    def fail(*args):
        raise RuntimeError("database failed")

    original_count = len(h.assets.blobs.objects)
    monkeypatch.setattr(h.store, "atomic", fail)
    with pytest.raises(RuntimeError):
        h.assets.save_asset("r", "g", "video", 2, b"data", "video/mp4")
    assert len(h.assets.blobs.objects) == original_count


def test_delete_failure_does_not_block_return_and_is_retried(h, monkeypatch):
    h.to_gesture()
    video = h.upload()["asset_id"]
    original_delete = h.assets.blobs.delete

    def fail(*args):
        raise RuntimeError("temporary deletion failure")

    monkeypatch.setattr(h.assets.blobs, "delete", fail)
    for uid in ("a", "b", "c"):
        h.post(f"/api/rooms/{h.room_id}/leave", uid)
    assert h.store.atomic(lambda tx: tx.get(f"rooms/{h.room_id}"))["status"] == "waiting"
    assert h.doc(f"/assets/{video}")
    monkeypatch.setattr(h.assets.blobs, "delete", original_delete)
    h.game.cleanup()
    assert h.doc(f"/assets/{video}") is None


def test_delayed_background_result_does_not_advance_or_overwrite_main_step(h):
    h.to_gesture()
    h.upload()
    h.post(f"/api/rounds/{h.round_id}/gesture/finish", "b", {"gesture_session_id": h.session}, 202)
    h.post(f"/api/rounds/{h.round_id}/steps/3/submit", "c", {"text": "猫"}, 202)
    before = h.doc()
    h.complete("gesture_read", 2, JobResult(ok=True, text="犬"))
    after = h.doc()
    assert after["current_step_index"] == before["current_step_index"] == 4
    assert after["revision"] == before["revision"]
    assert h.doc("/private/main")["outputs"]["3"]["text"] == "猫"


def test_fatal_ai_failure_keeps_history_until_individual_return(h):
    h.start()
    h.complete("image_gen", 0, JobResult(ok=False))
    assert h.get(f"/api/rounds/{h.round_id}/history", "c")["round_status"] == "failed"
    h.post(f"/api/rooms/{h.room_id}/leave", "a")
    h.get(f"/api/rounds/{h.round_id}/history", "a", expected=403)
    assert h.get(f"/api/rounds/{h.round_id}/history", "b")["round_status"] == "failed"


def test_repeated_start_and_finish_do_not_create_duplicate_jobs(h):
    h.lobby()
    body = {"request_id": str(uuid4())}
    result = h.post(f"/api/rooms/{h.room_id}/start", body=body, expected=202)
    assert h.post(f"/api/rooms/{h.room_id}/start", body=body, expected=202) == result
    h.round_id = result["round_id"]
    h.base = f"rooms/{h.room_id}/rounds/{h.round_id}"
    assert len(h.store.atomic(lambda tx: tx.list(h.base + "/jobs"))) == 1


def test_same_request_concurrent_submission_returns_same_acceptance(h):
    h.start()
    h.complete("image_gen", 0)
    body = {"request_id": str(uuid4()), "text": "犬"}

    def submit(_):
        return h.client.post(
            f"/api/rounds/{h.round_id}/steps/1/submit",
            headers={"Authorization": "Bearer local:a"},
            json=body,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(submit, range(4)))
    assert all(r.status_code == 202 for r in responses)
    assert len({r.text for r in responses}) == 1


def test_malformed_form_and_json_use_common_400(h):
    h.to_gesture()
    response = h.client.post(
        f"/api/rounds/{h.round_id}/gesture/video",
        headers={"Authorization": "Bearer local:b"},
        data={"gesture_session_id": "../unsafe", "request_id": str(uuid4())},
        files={"file": ("x.mp4", b"x", "video/mp4")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"
    response = h.client.post(
        "/api/rooms",
        headers={"Authorization": "Bearer local:a", "Content-Type": "application/json"},
        content=b"not-json",
    )
    assert response.status_code == 400


def test_job_payload_excludes_secret_inputs(h):
    h.start()
    job = next(msg for msg in h.tasks.messages.values() if msg["target"] == "worker")
    assert set(job["payload"]) == {
        "job_id",
        "kind",
        "room_id",
        "round_id",
        "step_index",
        "revision",
    }
    assert "text" not in str(job)


def test_safe_asset_permission_helper_never_grants_outsiders(h):
    h.start()
    h.complete("image_gen", 0)
    asset_id = h.doc("/private/main")["outputs"]["0"]["asset_id"]
    assert h.game.can_read_asset("a", h.round_id, asset_id)
    assert not h.game.can_read_asset("b", h.round_id, asset_id)
    assert not h.game.can_read_asset("outsider", h.round_id, asset_id)
    assert not h.game.can_read_asset("a", h.round_id, "missing")


def test_emulator_cannot_select_real_ai_and_unknown_mime_is_rejected(h):
    with pytest.raises(ValidationError):
        Settings(runtime_mode="emulator", ai_mode="real")
    with pytest.raises(ApiError):
        AssetStorage(h.store, h.assets.blobs).save_asset("r", "g", "video", 2, b"x", "text/html")


def test_odai_source_is_not_called_for_unauthorized_or_replayed_start(h):
    h.lobby()
    source = MagicMock()
    source.select.return_value = SimpleNamespace(text="fixture")
    h.game.odai_source = source
    h.post(f"/api/rooms/{h.room_id}/start", "b", expected=403)
    source.select.assert_not_called()
    body = {"request_id": str(uuid4())}
    h.post(f"/api/rooms/{h.room_id}/start", body=body, expected=202)
    h.post(f"/api/rooms/{h.room_id}/start", body=body, expected=202)
    source.select.assert_called_once()


def test_cleanup_database_failure_is_deferred_after_successful_return(h, monkeypatch):
    h.to_gesture()
    h.upload()

    def fail(*args):
        raise RuntimeError("metadata listing temporarily unavailable")

    monkeypatch.setattr(h.assets, "delete_round_assets", fail)
    for uid in ("a", "b", "c"):
        h.post(f"/api/rooms/{h.room_id}/leave", uid)
    assert h.store.atomic(lambda tx: tx.get(f"rooms/{h.room_id}"))["status"] == "waiting"
    assert h.store.atomic(lambda tx: tx.list("cleanup_outbox"))


def test_gesture_batch_bound_prevents_firestore_document_overflow(h):
    h.to_gesture()
    h.settings.gesture_batch_max_bytes = 1024
    batch = {
        "gesture_session_id": h.session,
        "sequence_number": 0,
        "mirrored": False,
        "samples": [{"timestamp_ms": n, "hands": []} for n in range(100)],
    }
    response = h.client.post(
        f"/api/rounds/{h.round_id}/gesture/batches",
        headers={"Authorization": "Bearer local:b"},
        json=batch,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert h.doc("/gesture_batches/0") is None
