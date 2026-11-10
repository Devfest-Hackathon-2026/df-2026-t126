import pytest

from common import storage
from common.enums import AssetKind
from common.storage import (
    AssetError,
    LocalBlobStore,
    MemoryAssetIndex,
    delete_round_assets,
    save_asset,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 10
WEBM = b"\x1a\x45\xdf\xa3" + b"x" * 10
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"x" * 10


@pytest.fixture
def env(tmp_path):
    idx = MemoryAssetIndex()
    storage.configure(LocalBlobStore(tmp_path), idx)
    return tmp_path, idx


def test_save_image_and_video_extensions(env):
    root, idx = env
    a = save_asset("r1", "rd1", AssetKind.image, 1, PNG, "image/png")
    v = save_asset("r1", "rd1", AssetKind.video, 2, MP4, "video/mp4")
    w = save_asset("r1", "rd1", AssetKind.video, 2, WEBM, "video/webm")
    docs = idx.list("r1", "rd1")
    assert docs[a].path.endswith(f"/images/{a}.png")
    assert docs[v].path.endswith(f"/videos/{v}.mp4") and docs[v].content_type == "video/mp4"
    assert docs[w].path.endswith(".webm")
    assert docs[a].step_index == 1
    assert (root / docs[v].path).read_bytes() == MP4


def test_rejects_bad_input(env):
    with pytest.raises(AssetError) as e:
        save_asset("r", "rd", AssetKind.video, 2, MP4, "video/quicktime")
    assert e.value.code == "UNSUPPORTED_MEDIA_TYPE"
    with pytest.raises(AssetError):  # 形式を偽る（mp4の中身をwebmと申告）
        save_asset("r", "rd", AssetKind.video, 2, MP4, "video/webm")
    with pytest.raises(AssetError) as e:
        save_asset("r", "rd", AssetKind.video, 2, WEBM + b"x" * 10_000_000, "video/webm")
    assert e.value.code == "PAYLOAD_TOO_LARGE"
    with pytest.raises(AssetError):
        save_asset("r", "rd", AssetKind.image, 1, b"", "image/png")


def test_delete_round_assets_only_that_round(env):
    root, idx = env
    image = save_asset("r1", "rd1", AssetKind.image, 1, PNG, "image/png")
    save_asset("r1", "rd1", AssetKind.video, 2, WEBM, "video/webm")
    keep = save_asset("r1", "rd2", AssetKind.image, 1, PNG, "image/png")
    paths = [d.path for d in idx.list("r1", "rd1").values() if d.kind == AssetKind.video]
    assert delete_round_assets("r1", "rd1") == 1
    assert all(not (root / p).exists() for p in paths)
    assert list(idx.list("r1", "rd1")) == [image]  # S1: only recordings are deleted.
    assert list(idx.list("r1", "rd2")) == [keep]
    assert delete_round_assets("r1", "rd1") == 0  # 2回目は何もしない


def test_index_failure_rolls_back_blob(env):
    root, idx = env

    def boom(*a):
        raise RuntimeError("firestore down")

    idx.put = boom
    with pytest.raises(RuntimeError):
        save_asset("r", "rd", AssetKind.image, 1, PNG, "image/png")
    assert not any(p.is_file() for p in root.rglob("*"))
