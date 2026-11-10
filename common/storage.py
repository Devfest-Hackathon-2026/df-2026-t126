"""Shared asset functions. Configure once in each API/Worker process at startup."""

import logging
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from uuid import uuid4

from backend_a.errors import ApiError
from common.enums import AssetKind
from common.models import VIDEO_EXTENSIONS, AssetDoc

logger = logging.getLogger(__name__)
IMAGE_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg"}


class AssetError(ApiError):
    """B-compatible error class, also handled by A's existing API envelope."""

    def __init__(self, code: str, message: str):
        super().__init__(code, 400, message)


class LocalBlobStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def _file(self, path):
        target = (self.root / path).resolve()
        if not target.is_relative_to(self.root):
            raise AssetError("INVALID_INPUT", "保存先が正しくありません")
        return target

    def put(self, path, data, content_type):
        target = self._file(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def get(self, path):
        try:
            return self._file(path).read_bytes()
        except FileNotFoundError as exc:
            raise ApiError("ASSET_NOT_FOUND", 404, "素材が見つかりません") from exc

    def delete(self, path):
        self._file(path).unlink(missing_ok=True)


class MemoryAssetIndex:
    def __init__(self):
        self.docs = {}

    def put(self, room_id, round_id, asset_id, doc):
        self.docs[(room_id, round_id, asset_id)] = doc

    def list(self, room_id, round_id):
        return {
            asset: doc
            for (room, rd, asset), doc in self.docs.items()
            if (room, rd) == (room_id, round_id)
        }

    def delete(self, room_id, round_id, asset_id):
        self.docs.pop((room_id, round_id, asset_id), None)


class _IndexTransaction:
    """Adapt B's asset-only index; never used for game-state transactions."""

    def __init__(self, index):
        self.index = index

    def _ids(self, path):
        parts = path.split("/")
        if (
            len(parts) not in (5, 6)
            or parts[0] != "rooms"
            or parts[2] != "rounds"
            or parts[4] != "assets"
        ):
            raise ValueError("Only asset paths are supported by the legacy index")
        return parts

    def get(self, path):
        parts = self._ids(path)
        doc = self.index.list(parts[1], parts[3]).get(parts[5])
        return doc.model_dump() if doc else None

    def list(self, path):
        parts = self._ids(path)
        return [(key, doc.model_dump()) for key, doc in self.index.list(parts[1], parts[3]).items()]

    def set(self, path, value):
        parts = self._ids(path)
        self.index.put(parts[1], parts[3], parts[5], AssetDoc.model_validate(value))

    def delete(self, path):
        parts = self._ids(path)
        self.index.delete(parts[1], parts[3], parts[5])


class _IndexStore:
    def __init__(self, index):
        self.index, self.lock = index, RLock()

    def atomic(self, callback):
        with self.lock:
            return callback(_IndexTransaction(self.index))


class MemoryBlobs:
    def __init__(self):
        self.objects = {}

    def put(self, path, data, content_type):
        self.objects[path] = (bytes(data), content_type)

    def get(self, path):
        try:
            return self.objects[path][0]
        except KeyError as exc:
            raise ApiError("ASSET_NOT_FOUND", 404, "素材が見つかりません") from exc

    def delete(self, path):
        self.objects.pop(path, None)


class GoogleBlobs:
    def __init__(self, bucket):
        self.bucket = bucket

    def put(self, path, data, content_type):
        self.bucket.blob(path).upload_from_string(
            data, content_type=content_type, if_generation_match=0
        )

    def get(self, path):
        from google.api_core.exceptions import NotFound

        try:
            return self.bucket.blob(path).download_as_bytes()
        except NotFound as exc:
            raise ApiError("ASSET_NOT_FOUND", 404, "素材が見つかりません") from exc

    def delete(self, path):
        from google.api_core.exceptions import NotFound

        try:
            self.bucket.blob(path).delete()
        except NotFound:
            pass


class GcsBlobStore(GoogleBlobs):
    """B's explicitly constructed SDK backend; local startup never uses it."""

    def __init__(self, bucket: str, project: str | None = None):
        from google.cloud import storage

        super().__init__(storage.Client(project=project).bucket(bucket))


class FirestoreAssetIndex:
    """B's explicit SDK index, retaining native Firestore Timestamp values."""

    def __init__(self, project: str | None = None):
        from google.cloud import firestore

        self.db = firestore.Client(project=project)

    def _col(self, room_id, round_id):
        return self.db.collection(f"rooms/{room_id}/rounds/{round_id}/assets")

    def put(self, room_id, round_id, asset_id, doc):
        self._col(room_id, round_id).document(asset_id).set(doc.model_dump())

    def list(self, room_id, round_id):
        return {
            doc.id: AssetDoc.model_validate(doc.to_dict())
            for doc in self._col(room_id, round_id).stream()
        }

    def delete(self, room_id, round_id, asset_id):
        self._col(room_id, round_id).document(asset_id).delete()


class AssetStorage:
    def __init__(self, store, blobs, clock=None):
        self.store, self.blobs = store, blobs
        self.clock = clock or (lambda: datetime.now(UTC))

    def save_asset(self, room_id, round_id, kind, step_index, data, content_type):
        kind = AssetKind(kind)
        extensions = VIDEO_EXTENSIONS if kind == AssetKind.video else IMAGE_EXTENSIONS
        if content_type not in extensions:
            raise ApiError("UNSUPPORTED_MEDIA_TYPE", 400, "対応していない形式です")
        asset_id = uuid4().hex
        directory = "videos" if kind == AssetKind.video else "images"
        path = (
            f"rooms/{room_id}/rounds/{round_id}/{directory}/{asset_id}.{extensions[content_type]}"
        )
        doc = AssetDoc(
            kind=kind,
            path=path,
            content_type=content_type,
            size_bytes=len(data),
            step_index=step_index,
            created_at=self.clock(),
        )
        # Blobs are written outside retryable transactions; metadata is published last.
        self.blobs.put(path, data, content_type)
        try:
            self.store.atomic(
                lambda tx: tx.set(
                    f"rooms/{room_id}/rounds/{round_id}/assets/{asset_id}", doc.model_dump()
                )
            )
        except Exception:
            try:
                self.blobs.delete(path)
            except Exception:
                logger.exception("Unreferenced asset cleanup failed")
            raise
        return asset_id

    def delete_round_assets(self, room_id, round_id):
        root = f"rooms/{room_id}/rounds/{round_id}/assets"
        docs = self.store.atomic(lambda tx: tx.list(root))
        deleted = 0
        for asset_id, doc in docs:
            if doc["kind"] != AssetKind.video:
                continue  # Images expire via the agreed 24-hour Storage lifecycle, not leave/start.
            try:
                self.blobs.delete(doc["path"])
                self.store.atomic(lambda tx, key=asset_id: tx.delete(f"{root}/{key}"))
                deleted += 1
            except Exception:
                logger.exception("Video cleanup deferred", extra={"asset_id": asset_id})
        return deleted


_storage = None


def configure_storage(storage: AssetStorage):
    global _storage
    _storage = storage


def configure(blobs, index):
    """Preserve B's explicit injection interface; no automatic cloud fallback."""
    configure_storage(AssetStorage(_IndexStore(index), blobs))


def save_asset(
    room_id: str, round_id: str, kind: AssetKind, step_index: int, data: bytes, content_type: str
) -> str:
    if _storage is None:
        raise RuntimeError("configure_storage must be called at process startup")
    from common.settings import get_settings

    settings = get_settings()
    if not data:
        raise AssetError("INVALID_INPUT", "空のデータです")
    limit = settings.video_max_bytes if kind == AssetKind.video else 20_000_000
    if len(data) > limit:
        raise AssetError("PAYLOAD_TOO_LARGE", "素材のサイズが大きすぎます")
    extensions = VIDEO_EXTENSIONS if kind == AssetKind.video else IMAGE_EXTENSIONS
    if content_type not in extensions:
        raise AssetError("UNSUPPORTED_MEDIA_TYPE", "素材の形式を確認してください")
    signatures = {
        "image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": data.startswith(b"\xff\xd8\xff"),
        "video/webm": data.startswith(b"\x1a\x45\xdf\xa3"),
        "video/mp4": len(data) >= 12 and data[4:8] == b"ftyp",
    }
    if not signatures.get(content_type) or (
        kind == AssetKind.video and content_type not in settings.allowed_video_types
    ):
        raise AssetError("UNSUPPORTED_MEDIA_TYPE", "素材の形式を確認してください")
    return _storage.save_asset(room_id, round_id, kind, step_index, data, content_type)


def delete_round_assets(room_id: str, round_id: str) -> int:
    if _storage is None:
        raise RuntimeError("configure_storage must be called at process startup")
    return _storage.delete_round_assets(room_id, round_id)
