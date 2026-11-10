"""Worker の入口（Cloud Run）。Cloud Tasks が POST /tasks/run を呼ぶ。"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Header, Response

from common.models import JobPayload, JobResult
from common.settings import get_settings
from worker.ai.base import AIClient
from worker.ai.mock import MockAIClient
from worker.handler import handle_job

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker")
app = FastAPI(title="gesture-relay worker")


def build_ai() -> AIClient:
    s = get_settings()
    if s.ai_mode == "real":
        from worker.ai.real import RealAIClient

        return RealAIClient(s)
    return MockAIClient(delay_s=s.mock_delay_s)


class LogSink:
    """仮の書き込み先（Firestore 実装ができるまで、ログに出すだけ）。"""

    async def write_job_result(self, p: JobPayload, result: JobResult, *, final: bool) -> None:
        log.info("write_job_result %s ok=%s", p.job_id, result.ok)

    async def advance_step(self, room_id: str, round_id: str) -> None:
        log.info("advance_step %s/%s", room_id, round_id)


@app.get("/health")
async def healthz() -> dict:
    return {"ok": True}


@app.post("/tasks/run")
async def run(payload: JobPayload, response: Response,
              x_cloudtasks_taskretrycount: int = Header(default=0)) -> dict:
    from worker.io_memory import MemoryJobIO  # 本番では Firestore/Storage 版に差し替える

    status = await handle_job(payload, x_cloudtasks_taskretrycount + 1,
                              ai=build_ai(), io=MemoryJobIO(), sink=LogSink())
    response.status_code = status
    return {"status": status}
