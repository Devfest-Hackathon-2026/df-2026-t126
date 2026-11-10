"""Cloud Tasks から呼ばれる処理。再試行の判断（500 / 200）をここで行う。"""
from __future__ import annotations

import logging
from typing import Protocol

from common.models import JOB_POLICY, JobPayload, JobResult
from worker.ai.base import AIClient
from worker.jobs import JobIO, run_job

log = logging.getLogger("worker")


class JobSink(Protocol):
    """結果の書き込み先。write_job_result は B、advance_step は A の共有部品。"""

    async def write_job_result(self, p: JobPayload, result: JobResult, *, final: bool) -> None: ...
    async def advance_step(self, room_id: str, round_id: str) -> None: ...


async def handle_job(payload: JobPayload, attempt: int, *, ai: AIClient, io: JobIO, sink: JobSink) -> int:
    """HTTPステータスを返す。500=Cloud Tasks に再配送させる、200=処理完了。

    attempt は 1 始まり（Cloud Tasks の X-CloudTasks-TaskRetryCount + 1）。
    """
    result = await run_job(payload, ai=ai, io=io)
    max_attempts = JOB_POLICY[payload.kind].max_attempts
    log.info("job=%s kind=%s attempt=%d ok=%s error=%s", payload.job_id, payload.kind.value, attempt, result.ok,
             result.error.code.value if result.error else None)

    if not result.ok and result.error and result.error.retryable and attempt < max_attempts:
        return 500  # 再試行する。まだ結果は確定させない

    await sink.write_job_result(payload, result, final=True)
    if result.ok:
        await sink.advance_step(payload.room_id, payload.round_id)
    return 200
