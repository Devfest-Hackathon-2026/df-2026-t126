"""メモリ上の JobIO（テストと、Firestore 実装ができるまでの仮）。"""
from __future__ import annotations

import uuid

from worker.ai.mock import _PNG

from common.models import GestureBatch, JobPayload


class MemoryJobIO:
    def __init__(self, odai="走っているいぬ", text: str | None = None, conclusion="走っているいぬ", image=_PNG,
                 batches: list[GestureBatch] | None = None):
        self.odai, self.text, self.conclusion, self.image = odai, text, conclusion, image
        self.batches = batches or []
        self.saved: dict[str, bytes] = {}

    async def load_odai(self, p: JobPayload) -> str: return self.odai
    async def load_text(self, p: JobPayload) -> str | None: return self.text
    async def load_image(self, p: JobPayload) -> bytes: return self.image
    async def load_batches(self, p: JobPayload) -> list[GestureBatch]: return self.batches
    async def load_conclusion(self, p: JobPayload) -> str: return self.conclusion

    async def save_image(self, p: JobPayload, data: bytes) -> str:
        asset_id = uuid.uuid4().hex
        self.saved[asset_id] = data
        return asset_id
