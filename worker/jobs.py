"""run_job: AIを呼んで結果を返す（Firestore の進行状態は書かない）。

入力の読み出し・画像の保存は JobIO に任せる（本番は Firestore/Storage、テストはメモリ）。
"""
from __future__ import annotations

from typing import Protocol

from common.enums import ErrorCode, JobKind
from common.models import ErrorInfo, GestureBatch, JobPayload, JobResult
from worker.ai.base import AIClient, AIError, cosine
from worker.prompts import build_first_image_prompt, build_image_prompt


class JobIO(Protocol):
    async def load_odai(self, p: JobPayload) -> str: ...
    async def load_text(self, p: JobPayload) -> str | None: ...        # 前の段の文章（人A/Cの入力）
    async def load_image(self, p: JobPayload) -> bytes: ...            # 結論に使う最終画像
    async def load_batches(self, p: JobPayload) -> list[GestureBatch]: ...
    async def load_conclusion(self, p: JobPayload) -> str: ...
    async def save_image(self, p: JobPayload, data: bytes) -> str: ... # asset_id を返す


def _error(e: Exception) -> JobResult:
    if isinstance(e, AIError):
        info = ErrorInfo(code=e.code, message=str(e), retryable=e.retryable)
    else:
        info = ErrorInfo(code=ErrorCode.ai_failed, message=f"{type(e).__name__}: {e}"[:200], retryable=True)
    return JobResult(ok=False, error=info)


async def run_job(payload: JobPayload, *, ai: AIClient, io: JobIO) -> JobResult:
    try:
        if payload.kind == JobKind.image_gen:
            text = await io.load_text(payload)
            if text is None:  # 最初の段（お題から）
                prompt = build_first_image_prompt(await io.load_odai(payload))
            else:
                prompt = build_image_prompt(text)
            data = await ai.generate_image(prompt)
            return JobResult(ok=True, asset_id=await io.save_image(payload, data))

        if payload.kind == JobKind.gesture_read:
            return JobResult(ok=True, text=await ai.read_gesture(await io.load_batches(payload)))

        if payload.kind == JobKind.conclude:
            return JobResult(ok=True, text=await ai.conclude(await io.load_image(payload)))

        if payload.kind == JobKind.similarity:
            odai = await io.load_odai(payload)
            conclusion = await io.load_conclusion(payload)
            a, b = await ai.embed(odai), await ai.embed(conclusion)
            return JobResult(ok=True, score=cosine(a, b))

        return JobResult(ok=False, error=ErrorInfo(code=ErrorCode.invalid_input, message="unknown kind", retryable=False))
    except Exception as e:  # noqa: BLE001
        return _error(e)
