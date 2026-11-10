from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from common.models import JobResult
from tests.conftest import video_bytes


def test_full_three_player_game_history_and_cleanup(h):
    h.start()
    rid, room = h.round_id, h.room_id
    assert h.get(f"/api/rounds/{rid}/history")["steps"] == []
    h.complete("image_gen", 0)
    first = h.get(f"/api/rounds/{rid}/my-input")["input"]["asset_id"]
    assert h.get(f"/api/rounds/{rid}/my-input", "c", expected=403)
    assert (
        h.client.get(
            f"/api/rounds/{rid}/assets/{first}", headers={"Authorization": "Bearer local:a"}
        ).status_code
        == 200
    )
    h.get(f"/api/rounds/{rid}/assets/{first}", "b", expected=403)
    h.post(f"/api/rounds/{rid}/steps/1/submit", body={"text": "犬が走る"}, expected=202)
    assert h.get(f"/api/rounds/{rid}/my-input", "b")["input"] == {
        "kind": "text",
        "text": "犬が走る",
    }
    h.session = h.post(f"/api/rounds/{rid}/gesture/start", "b")["gesture_session_id"]
    h.post(f"/api/rounds/{rid}/gesture/finish", "b", {"gesture_session_id": h.session}, 202)
    assert h.step(3)["status"] == "waiting"
    video = h.upload()["asset_id"]
    assert h.step(3)["status"] == "active"
    assert h.get(f"/api/rounds/{rid}/my-input", "c")["input"]["asset_id"] == video
    h.get(f"/api/rounds/{rid}/assets/{video}", "a", expected=403)
    h.complete("gesture_read", 2)
    h.post(f"/api/rounds/{rid}/steps/3/submit", "c", {"text": "犬"}, 202)
    h.complete("image_gen", 4)
    h.complete("conclude", 5)
    h.complete("similarity")
    for uid in ("a", "b", "c"):
        history = h.get(f"/api/rounds/{rid}/history", uid)
        assert len(history["steps"]) == 6
        assert history["result"]["similarity"] == 0.8
    h.post(f"/api/rooms/{room}/leave")
    h.get(f"/api/rounds/{rid}/history", "a", expected=403)
    h.get(f"/api/rounds/{rid}/assets/{video}", "a", expected=403)
    assert h.get(f"/api/rounds/{rid}/history", "c")["round_status"] == "finished"
    h.post(f"/api/rooms/{room}/leave", "b")
    assert h.doc(f"/assets/{video}") is not None
    h.post(f"/api/rooms/{room}/leave", "c")
    assert h.doc(f"/assets/{video}") is None
    assert h.doc(f"/assets/{first}") is not None
    assert h.store.atomic(lambda tx: tx.get(f"rooms/{room}"))["status"] == "waiting"
    h.start()  # next round cannot restore old history access
    h.get(f"/api/rounds/{rid}/history", "c", expected=403)


def test_upload_first_then_finish_and_missing_finish_timeout(h):
    h.to_gesture()
    h.upload()
    assert h.step(3)["status"] == "waiting"
    deadline = {
        "room_id": h.room_id,
        "round_id": h.round_id,
        "kind": "step",
        "step_index": 2,
        "revision": h.doc()["revision"],
    }
    h.clock.advance(27)
    h.game.deadline(deadline)
    assert h.step(2)["status"] == "active"
    assert h.step(3)["status"] == "waiting"
    h.clock.advance(1)  # countdown 15 + recording 8 + grace 5 = 28
    h.game.deadline(deadline)
    assert h.step(3)["status"] == "active"
    assert h.step(2)["timed_out"]


def test_same_request_replays_after_state_change_and_rejects_changed_body(h):
    h.start()
    h.complete("image_gen", 0)
    body = {"request_id": str(uuid4()), "text": " ", "is_auto": True}
    path = f"/api/rounds/{h.round_id}/steps/1/submit"
    first = h.post(path, body=body, expected=202)
    assert h.post(path, body=body, expected=202) == first
    h.post(path, body={**body, "text": "changed"}, expected=400)
    h.post(path, body={"text": "second request"}, expected=409)
    assert h.doc("/private/main")["outputs"]["1"]["text"] == " "


@pytest.mark.parametrize("_iteration", range(5))
def test_concurrent_submissions_are_committed_once(h, _iteration):
    h.start()
    h.complete("image_gen", 0)
    path = f"/api/rounds/{h.round_id}/steps/1/submit"

    def submit(_):
        return h.client.post(
            path,
            headers={"Authorization": "Bearer local:a"},
            json={"request_id": str(uuid4()), "text": "race"},
        ).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(submit, range(12)))
    assert statuses.count(202) == 1
    assert statuses.count(409) == 11
    assert h.doc()["current_step_index"] == 2


def test_permissions_consent_roles_capacity_host_and_input(h):
    h.post("/api/rooms", body={"name": "a", "consented": False}, expected=403)
    h.lobby()
    room = h.room_id
    h.post("/api/rooms/join", "d", {"name": "d", "consented": True, "join_code": h.code}, 409)
    h.post(f"/api/rooms/{room}/role", "a", {"role": "B"}, 409)
    h.post(f"/api/rooms/{room}/role", "outsider", {"role": "A"}, 403)
    h.post(f"/api/rooms/{room}/start", "b", expected=403)
    h.start()
    h.post(f"/api/rooms/{room}/role", "a", {"role": None}, 409)
    h.get(f"/api/rounds/{h.round_id}/history", "outsider", expected=403)
    h.complete("image_gen", 0)
    h.post(f"/api/rounds/{h.round_id}/steps/1/submit", "b", {"text": "wrong"}, 403)
    h.post(f"/api/rounds/{h.round_id}/steps/1/submit", body={"text": "x" * 2001}, expected=400)


@pytest.mark.parametrize("dropped", [False, True])
def test_deadline_distinguishes_communication_and_dropout(h, dropped):
    h.start()
    h.complete("image_gen", 0)
    revision = h.doc()["revision"]
    h.clock.advance(66)
    if not dropped:
        h.post(f"/api/rooms/{h.room_id}/heartbeat")
    payload = {
        "kind": "step",
        "room_id": h.room_id,
        "round_id": h.round_id,
        "step_index": 1,
        "revision": revision,
    }
    h.game.deadline(payload)
    h.game.deadline(payload)
    room = h.store.atomic(lambda tx: tx.get(f"rooms/{h.room_id}"))
    assert room["fail_reason"] == ("player_dropped" if dropped else "communication_failed")
    assert h.doc()["status"] == "failed"
    assert len(h.get(f"/api/rounds/{h.round_id}/history", "c")["steps"]) == 6


def test_grace_period_and_late_rejection(h):
    h.start()
    h.complete("image_gen", 0)
    h.clock.advance(64)
    h.post(
        f"/api/rounds/{h.round_id}/steps/1/submit",
        body={"text": "late", "is_auto": True},
        expected=202,
    )
    assert h.step(1)["timed_out"]
    assert h.step(2)["status"] == "active"


def test_watchdog_detects_nonacting_player_dropout_during_ai(h):
    h.start()
    h.clock.advance(15)
    h.post(f"/api/rooms/{h.room_id}/heartbeat", "a")
    h.post(f"/api/rooms/{h.room_id}/heartbeat", "b")
    h.game.deadline({"kind": "watchdog", "room_id": h.room_id, "round_id": h.round_id})
    assert h.doc()["status"] == "failed"


def test_gesture_batches_sequence_dedup_and_gap(h):
    h.to_gesture()
    path = f"/api/rounds/{h.round_id}/gesture/batches"
    batch = {
        "gesture_session_id": h.session,
        "sequence_number": 3,
        "mirrored": False,
        "samples": [{"timestamp_ms": 0, "hands": []}],
    }

    def send(value, status=202):
        response = h.client.post(path, headers={"Authorization": "Bearer local:b"}, json=value)
        assert response.status_code == status, response.text

    send(batch)
    send({**batch, "samples": []})
    assert len(h.doc("/gesture_batches/3")["samples"]) == 1
    send({**batch, "sequence_number": 7})
    send({**batch, "sequence_number": -1}, 400)
    send({**batch, "gesture_session_id": "wrong"}, 409)
    send(
        {
            **batch,
            "samples": [{"timestamp_ms": 0, "hands": [{"handedness": "Right", "landmarks": []}]}],
        },
        400,
    )


def test_gesture_background_failure_does_not_stop_main(h):
    h.to_gesture()
    h.upload()
    h.post(f"/api/rounds/{h.round_id}/gesture/finish", "b", {"gesture_session_id": h.session}, 202)
    h.complete("gesture_read", 2, JobResult(ok=False))
    assert h.doc()["gesture_ai_status"] == "failed"
    assert h.doc()["status"] == "playing"
    assert h.step(3)["status"] == "active"


def test_video_validation_replay_size_type_and_duration(h):
    h.to_gesture()
    h.upload(data=b"not video", expected=400)
    h.upload(data=b"fake", mime="text/plain", expected=400)
    h.upload(data=video_bytes(9), expected=400)
    request_id = str(uuid4())
    recording = video_bytes(8)
    first = h.upload(request_id=request_id, data=recording)
    assert h.upload(request_id=request_id, data=recording) == first
    assert len(h.store.atomic(lambda tx: tx.list(h.base + "/assets"))) == 2
    h.settings.video_max_bytes = 100
    h.upload(expected=400)


def test_webm_extension_and_mime_follow_actual_format_not_filename(h):
    h.to_gesture()
    video = h.upload(data=video_bytes(container_format="webm"), mime="video/webm")["asset_id"]
    doc = h.doc(f"/assets/{video}")
    assert doc["path"].endswith(".webm")
    assert doc["content_type"] == "video/webm"
    h.post(f"/api/rounds/{h.round_id}/gesture/finish", "b", {"gesture_session_id": h.session}, 202)
    data, mime = h.game.get_asset("c", h.round_id, video)
    assert data.startswith(b"\x1a\x45\xdf\xa3")
    assert mime == "video/webm"


def test_video_upload_rejects_unexpected_codec_and_accepts_fragmented_mp4(h):
    h.to_gesture()
    unsupported = video_bytes(container_format="mov", encoder="magicyuv")
    response = h.upload(data=unsupported, expected=400)
    assert response["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    recording = video_bytes(options={"movflags": "frag_keyframe+empty_moov"})
    assert h.upload(data=recording)["asset_id"]


def test_auth_internal_routes_validation_and_common_errors(h):
    assert h.client.post("/api/rooms", json={}).status_code == 401
    assert (
        h.client.post(
            "/api/rooms", headers={"Authorization": "Bearer garbage"}, json={}
        ).status_code
        == 401
    )
    h.post("/api/rooms", body={"name": " ", "consented": True}, expected=400)
    assert h.client.post("/internal/deadlines", json={}).status_code == 404
    assert h.client.get("/not-found").json()["error"]["code"] == "ROOM_NOT_FOUND"


def test_advance_is_idempotent_and_old_round_deadline_is_noop(h):
    h.start()
    h.complete("image_gen", 0)
    before = h.doc()
    for _ in range(3):
        h.game.advance_step(h.room_id, h.round_id)
    assert h.doc() == before
    h.game.deadline(
        {
            "kind": "step",
            "room_id": h.room_id,
            "round_id": h.round_id,
            "step_index": 3,
            "revision": 0,
        }
    )
    assert h.doc() == before
