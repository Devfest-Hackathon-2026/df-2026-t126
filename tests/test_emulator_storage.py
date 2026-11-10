import os

import pytest

from backend_a.runtime import localhost_endpoint
from common.storage import GoogleBlobs


@pytest.mark.skipif(
    os.environ.get("RUN_FIRESTORE_EMULATOR_TESTS") != "1", reason="Requires local Storage emulator"
)
def test_storage_sdk_upload_playback_and_delete(h, monkeypatch):
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import storage

    host = os.environ.get("FIREBASE_STORAGE_EMULATOR_HOST", "")
    localhost_endpoint(host)
    endpoint = f"http://{host}"
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", endpoint)
    client = storage.Client(
        project="demo-gesture-relay",
        credentials=AnonymousCredentials(),
        client_options={"api_endpoint": endpoint},
    )
    h.assets.blobs = GoogleBlobs(client.bucket("demo-gesture-relay.appspot.com"))
    h.to_gesture()
    video = h.upload()["asset_id"]
    assert h.step(3)["status"] == "waiting"
    h.post(f"/api/rounds/{h.round_id}/gesture/finish", "b", {"gesture_session_id": h.session}, 202)
    data, content_type = h.game.get_asset("c", h.round_id, video)
    assert data[4:8] == b"ftyp"
    assert content_type == "video/mp4"
    for uid in ("a", "b", "c"):
        h.post(f"/api/rooms/{h.room_id}/leave", uid)
    assert h.doc(f"/assets/{video}") is None
