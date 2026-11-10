"""Private composition of B's handler and A's injected persistence adapters.

No global app, AI factory or credentials discovery: the caller explicitly injects
an authorized runtime and AI client. B's worker/main.py is preserved verbatim.
"""

import asyncio
from typing import Annotated

from fastapi import Depends, Header
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from api.app import create_app
from backend_a.errors import ApiError
from backend_a.worker_bridge import WorkerBridge
from common.models import JobPayload


def create_worker_app(runtime, ai, **bridge_options):
    app = create_app(runtime, internal=True)
    bridge = WorkerBridge(runtime.game, ai, **bridge_options)
    app.state.worker_bridge = bridge

    def verify_task(authorization: Annotated[str | None, Header()] = None):
        if not authorization or not authorization.startswith("Bearer "):
            raise ApiError("UNAUTHENTICATED", 401, "内部認証が必要です")
        runtime.internal_auth.verify(authorization[7:])

    # Retain B's /tasks/run and accept A's previously configured internal target.
    @app.post("/tasks/run", dependencies=[Depends(verify_task)])
    @app.post("/internal/jobs", dependencies=[Depends(verify_task)])
    async def run(
        payload: JobPayload, x_cloudtasks_taskretrycount: Annotated[int, Header(ge=0)] = 0
    ):
        try:
            status = await run_in_threadpool(
                lambda: asyncio.run(bridge.handle(payload, retry_count=x_cloudtasks_taskretrycount))
            )
        except ValueError as exc:
            raise ApiError("INVALID_INPUT", 400, "ジョブの情報を確認してください") from exc
        return JSONResponse({"status": status}, status_code=status)

    return app
