"""Export real A HTTP/B mock-Worker responses for frontend TypeScript assignment checks.

Run from the repository with .venv/bin/python tools/export_frontend_contracts.py.
Uses only in-memory services and forbids sockets. Does not modify frontend source.
"""

import asyncio
import json
import socket
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def export():
    from backend_a.worker_bridge import WorkerBridge
    from tests.conftest import Harness
    from worker.ai.mock import MockAIClient

    h = Harness()
    bridge = WorkerBridge(h.game, MockAIClient())
    fixtures = []

    def record(kind, data):
        fixtures.append((kind, data))
        return data

    def deliver(kind, index=None):
        assert asyncio.run(bridge.handle(h.pending_job(kind, index))) == 200

    try:
        room = record(
            "CreateRoomResponse", h.post("/api/rooms", body={"name": "A", "consented": True})
        )
        h.room_id, h.code = room["room_id"], room["join_code"]
        for uid in ("b", "c"):
            record(
                "JoinRoomResponse",
                h.post(
                    "/api/rooms/join", uid, {"name": uid, "consented": True, "join_code": h.code}
                ),
            )
        for uid in ("a", "b", "c"):
            record(
                "AcceptedResponse",
                h.post(f"/api/rooms/{h.room_id}/role", uid, {"role": uid.upper()}),
            )
        start = record("StartGameResponse", h.post(f"/api/rooms/{h.room_id}/start", expected=202))
        from backend_a.game import root

        h.round_id = start["round_id"]
        h.base = root(h.room_id, h.round_id)
        deliver("image_gen", 0)
        record("MyInputResponse", h.get(f"/api/rounds/{h.round_id}/my-input"))
        h.post(f"/api/rounds/{h.round_id}/steps/1/submit", body={"text": "犬"}, expected=202)
        record("MyInputResponse", h.get(f"/api/rounds/{h.round_id}/my-input", "b"))
        gesture = record(
            "GestureStartResponse", h.post(f"/api/rounds/{h.round_id}/gesture/start", "b")
        )
        h.session = gesture["gesture_session_id"]
        record("GestureVideoResponse", h.upload())
        h.post(
            f"/api/rounds/{h.round_id}/gesture/finish", "b", {"gesture_session_id": h.session}, 202
        )
        record("MyInputResponse", h.get(f"/api/rounds/{h.round_id}/my-input", "c"))
        deliver("gesture_read", 2)
        record("HistoryResponse", h.get(f"/api/rounds/{h.round_id}/history", "a"))
        h.post(f"/api/rounds/{h.round_id}/steps/3/submit", "c", {"text": "犬"}, 202)
        deliver("image_gen", 4)
        deliver("conclude", 5)
        deliver("similarity")
        record("HistoryResponse", h.get(f"/api/rounds/{h.round_id}/history", "c"))
    finally:
        h.client.close()
    from fastapi.encoders import jsonable_encoder

    room_doc = h.store.atomic(lambda tx: tx.get(f"rooms/{h.room_id}"))
    record("RoomDoc", jsonable_encoder(room_doc))
    record("RoundDoc", jsonable_encoder(h.doc()))
    for _, doc in h.store.atomic(lambda tx: tx.list(h.base + "/steps")):
        record("StepDoc", jsonable_encoder(doc))
    for _, doc in h.store.atomic(lambda tx: tx.list(f"rooms/{h.room_id}/players")):
        record("PlayerDoc", jsonable_encoder(doc))
    # Assignment through a const permits compatible extra private/internal fields.
    lines = ['import type * as API from "../frontend/src/api/types";']
    for index, (kind, value) in enumerate(fixtures):
        lines.append(f"const actual{index} = {json.dumps(value, ensure_ascii=False)} as const;")
        # JSON arrays are mutable on the wire; remove deep readonly from fixture literals.
        lines.append(
            f"const check{index}: API.{kind} = structuredClone(actual{index}) as Mutable<typeof actual{index}>;"
        )
    lines.append("type Mutable<T> = { -readonly [P in keyof T]: Mutable<T[P]> };")
    target = ROOT / ".tools/frontend-api-contracts.ts"
    target.parent.mkdir(exist_ok=True)
    target.write_text("\n".join(lines) + "\n")
    print(f"Exported {len(fixtures)} real responses/public documents to {target}")


if __name__ == "__main__":
    # No emulator or credentials; no connection is possible even if ambient env exists.
    import os

    os.environ.pop("RUN_FIRESTORE_EMULATOR_TESTS", None)
    with patch.object(socket.socket, "connect", side_effect=AssertionError("offline only")):
        export()
