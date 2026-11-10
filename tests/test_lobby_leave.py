"""ロビー（待機中）での退出と、ホストの交代。ゲームが始まる前は、部屋から外れられる。"""


def _room(h):
    return h.store.atomic(lambda tx: tx.get(f"rooms/{h.room_id}"))


def _players(h):
    return dict(h.store.atomic(lambda tx: tx.list(f"rooms/{h.room_id}/players")))


def test_lobby_leave_removes_player_and_frees_role(h):
    h.lobby()
    assert h.post(f"/api/rooms/{h.room_id}/leave", "c") == {"accepted": True}
    players = _players(h)
    assert set(players) == {"a", "b"}
    assert _room(h)["host_player_id"] == "a"  # ホストでない人が出ても、ホストは変わらない
    assert _room(h)["status"] == "waiting"
    # 空いた枠に、別の人が入れる。役割も空く
    h.post(
        "/api/rooms/join", "d", {"name": "d", "consented": True, "join_code": h.code}
    )
    h.post(f"/api/rooms/{h.room_id}/role", "d", {"role": "C"})
    assert _players(h)["d"]["role"] == "C"


def test_host_leaving_lobby_passes_host_to_next_in_join_order(h):
    h.lobby()
    # 参加の早い順を固定する（同じ時刻でも順序が決まるように、b を先に）
    def order(tx):
        for uid, minutes in (("a", 0), ("b", 1), ("c", 2)):
            p = tx.get(f"rooms/{h.room_id}/players/{uid}")
            p["consented_at"] = p["consented_at"].replace(microsecond=minutes)
            tx.set(f"rooms/{h.room_id}/players/{uid}", p)

    h.store.atomic(order)
    h.post(f"/api/rooms/{h.room_id}/leave", "a")
    assert set(_players(h)) == {"b", "c"}
    assert _room(h)["host_player_id"] == "b"
    # 元のホストは、もう開始できない。新しいホストは、2人では開始できない（3人そろっていない）
    h.post(f"/api/rooms/{h.room_id}/start", "a", expected=403)


def test_empty_room_next_joiner_becomes_host(h):
    h.lobby()
    for uid in ("a", "b", "c"):
        h.post(f"/api/rooms/{h.room_id}/leave", uid)
    assert _players(h) == {}
    h.post("/api/rooms/join", "d", {"name": "d", "consented": True, "join_code": h.code})
    assert _room(h)["host_player_id"] == "d"


def test_leave_requires_membership(h):
    h.lobby()
    h.post(f"/api/rooms/{h.room_id}/leave", "x", expected=403)
    assert set(_players(h)) == {"a", "b", "c"}


def test_leave_replay_with_same_request_is_safe(h):
    h.lobby()
    from uuid import uuid4

    body = {"request_id": str(uuid4())}
    for _ in range(2):
        response = h.client.post(
            f"/api/rooms/{h.room_id}/leave",
            headers={"Authorization": "Bearer local:c"},
            json=body,
        )
        assert response.status_code == 200, response.text
    assert set(_players(h)) == {"a", "b"}
