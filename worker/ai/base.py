"""AIクライアントの共通部分（shared-types.md §5）。"""
from __future__ import annotations

import math
from typing import Protocol

from common.enums import ErrorCode
from common.models import GestureBatch


class AIError(Exception):
    """AI呼び出しの失敗。run_job が ErrorInfo に変換する。"""

    def __init__(self, code: ErrorCode, message: str, retryable: bool):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class AIClient(Protocol):
    async def generate_image(self, prompt: str) -> bytes: ...
    async def read_gesture(self, batches: list[GestureBatch]) -> str: ...
    async def conclude(self, image: bytes) -> str: ...
    async def embed(self, text: str) -> list[float]: ...


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
