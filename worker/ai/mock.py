"""モックAI。本物のAIなしで、通しの動作確認ができる。"""
from __future__ import annotations

import asyncio
import base64
import hashlib

from common.models import GestureBatch

# 1x1 の透明PNG
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


class MockAIClient:
    def __init__(self, delay_s: float = 0.0, conclusion: str = "走っているいぬ", gesture_text: str = "手を左右に振っている"):
        self.delay_s = delay_s
        self.conclusion = conclusion
        self.gesture_text = gesture_text

    async def _wait(self) -> None:
        if self.delay_s:
            await asyncio.sleep(self.delay_s)

    async def generate_image(self, prompt: str) -> bytes:
        await self._wait()
        return _PNG

    async def read_gesture(self, batches: list[GestureBatch]) -> str:
        await self._wait()
        return self.gesture_text

    async def conclude(self, image: bytes) -> str:
        await self._wait()
        return self.conclusion

    async def embed(self, text: str) -> list[float]:
        await self._wait()
        # 同じ文字列は同じベクトル、近い文字列は少し近くなる簡易版
        h = hashlib.sha256(text.encode()).digest()
        vec = [b / 255 for b in h[:16]]
        for ch in text:
            vec[ord(ch) % 16] += 0.5
        return vec
