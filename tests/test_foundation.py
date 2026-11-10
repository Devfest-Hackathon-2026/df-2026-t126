from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from backend_a.auth import DenyInternalAuth, LocalAuth
from backend_a.errors import ApiError
from backend_a.store import MemoryStore
from common.enums import AssetKind
from common.models import JOB_POLICY, GestureBatch
from common.settings import Settings
from common.storage import AssetStorage, MemoryBlobs


def test_cloud_disabled_by_default():
    assert Settings().runtime_mode == "local"
    with pytest.raises(ValidationError):
        Settings(runtime_mode="cloud")
    with pytest.raises(ValidationError):
        Settings(runtime_mode="emulator", project_id="production")


def test_transaction_rolls_back_and_serializes():
    store = MemoryStore()
    store.atomic(lambda tx: tx.set("c/counter", {"n": 0}))

    def increment(_):
        def work(tx):
            doc = tx.get("c/counter")
            tx.set("c/counter", {"n": doc["n"] + 1})

        store.atomic(work)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(increment, range(40)))
    assert store.atomic(lambda tx: tx.get("c/counter"))["n"] == 40

    def fail(tx):
        tx.set("c/counter", {"n": -1})
        raise RuntimeError("rollback")

    with pytest.raises(RuntimeError):
        store.atomic(fail)
    assert store.atomic(lambda tx: tx.get("c/counter"))["n"] == 40


def test_auth_and_gesture_validation():
    assert LocalAuth().verify("local:alice") == "alice"
    for token in ["", "local:../bob", "a-real-token"]:
        with pytest.raises(ApiError):
            LocalAuth().verify(token)
    with pytest.raises(ApiError):
        DenyInternalAuth().verify("local:alice")
    with pytest.raises(ValidationError):
        GestureBatch(gesture_session_id="g", sequence_number=-1, mirrored=False, samples=[])
    assert sum(not p.fatal for p in JOB_POLICY.values()) == 1


def test_video_cleanup_preserves_images_and_missing_blobs_are_404():
    store, blobs = MemoryStore(), MemoryBlobs()
    storage = AssetStorage(store, blobs)
    storage.save_asset("room", "round", AssetKind.image, 0, b"image", "image/png")
    storage.save_asset("room", "round", AssetKind.video, 2, b"video", "video/mp4")
    assert storage.delete_round_assets("room", "round") == 1
    assert storage.delete_round_assets("room", "round") == 0
    assert len(blobs.objects) == 1
    with pytest.raises(ApiError) as exc:
        blobs.get("missing")
    assert exc.value.status == 404
