from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4


def create(h, uid, request_id=None, expected=200):
    return h.post(
        "/api/rooms",
        uid,
        {"name": uid, "consented": True, "request_id": request_id or str(uuid4())},
        expected,
    )


def test_room_create_limit_preserves_idempotency_and_resets(h):
    h.settings.room_create_uid_limit = 1
    request_id = str(uuid4())
    room = create(h, "a", request_id)
    assert create(h, "a", request_id) == room
    assert create(h, "a", expected=429)["error"]["code"] == "TOO_MANY_ATTEMPTS"
    assert create(h, "b")["room_id"] != room["room_id"]
    h.clock.advance(60)
    assert create(h, "a")["room_id"] != room["room_id"]


def test_optional_room_create_limit_counts_distinct_uids_atomically(h):
    h.settings.room_create_global_limit = 1

    def post(uid):
        return h.client.post(
            "/api/rooms",
            headers={"Authorization": f"Bearer local:{uid}"},
            json={"name": uid, "consented": True, "request_id": str(uuid4())},
        ).status_code

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(post, ("a", "b"))) == [200, 429]
    assert len(h.store.atomic(lambda tx: tx.list("join_codes"))) == 1


def test_global_round_start_limit_does_not_queue_a_job_for_rejected_room(h):
    h.settings.round_start_global_limit = 1
    rooms = []
    for host in ("a", "d"):
        room = create(h, host)
        room_id = room["room_id"]
        for uid in ("b", "c"):
            h.post(
                "/api/rooms/join",
                uid,
                {"name": uid, "consented": True, "join_code": room["join_code"]},
            )
        for uid, role in ((host, "A"), ("b", "B"), ("c", "C")):
            h.post(f"/api/rooms/{room_id}/role", uid, {"role": role})
        rooms.append(room_id)

    request_id = str(uuid4())
    first = h.post(f"/api/rooms/{rooms[0]}/start", "a", {"request_id": request_id}, 202)
    assert h.post(f"/api/rooms/{rooms[0]}/start", "a", {"request_id": request_id}, 202) == first
    rejected = h.post(f"/api/rooms/{rooms[1]}/start", "d", expected=429)
    assert rejected["error"]["code"] == "TOO_MANY_ATTEMPTS"
    assert sum(message["target"] == "worker" for message in h.tasks.messages.values()) == 1
    h.clock.advance(60)
    h.post(f"/api/rooms/{rooms[1]}/start", "d", expected=202)
    assert sum(message["target"] == "worker" for message in h.tasks.messages.values()) == 2
