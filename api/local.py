"""Opt-in local team demo: public API + B mock AI + in-process task delivery.

Not a Cloud Tasks/production Worker entry point. Run one process, never reload
multiple workers with an in-memory queue. Local/emulator runtimes only.
"""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta

from api.app import create_app
from backend_a.runtime import build_runtime
from backend_a.tasks import MemoryTasks, dispatch_outbox
from backend_a.worker_bridge import WorkerBridge
from common.models import JobPayload
from common.settings import Settings
from worker.ai.mock import MockAIClient

logger = logging.getLogger(__name__)


class LocalDispatcher:
    def __init__(self, runtime):
        if (
            runtime.settings.runtime_mode not in ("local", "emulator")
            or runtime.settings.enable_cloud
            or runtime.settings.ai_mode != "mock"
            or not isinstance(runtime.game.tasks, MemoryTasks)
        ):
            raise ValueError("Local demo requires offline/emulator runtime and mock tasks/AI")
        self.game = runtime.game
        self.bridge = WorkerBridge(self.game, MockAIClient(delay_s=runtime.settings.mock_delay_s))
        self.receipts = {}

    async def tick(self):
        await asyncio.to_thread(dispatch_outbox, self.game.store, self.game.tasks)
        for task_id, message in list(self.game.tasks.messages.items()):
            now = self.game.clock()
            attempts, retry_at, done = self.receipts.get(task_id, (0, now, False))
            due = message.get("schedule_at")
            if isinstance(due, str):
                due = datetime.fromisoformat(due)
            if done or now < retry_at or (due and now < due):
                continue
            status = 500
            try:
                if message["target"] == "worker":
                    payload = JobPayload.model_validate(message["payload"])
                    status = await asyncio.to_thread(
                        lambda p=payload, n=attempts: asyncio.run(
                            self.bridge.handle(p, retry_count=n)
                        )
                    )
                elif message["target"] == "deadline":
                    await asyncio.to_thread(self.game.deadline, message["payload"])
                    status = 200
                else:
                    raise ValueError("Unknown local task target")
            except Exception:
                logger.exception("Local task delivery failed", extra={"task_id": task_id})
            attempts += 1
            self.receipts[task_id] = (
                attempts,
                now + timedelta(seconds=1),
                status == 200 or attempts >= 3,
            )


def build_local_app(runtime=None):
    if runtime is None:
        settings = Settings()
        # Reject before constructing any SDK client or discovering credentials.
        if settings.runtime_mode not in ("local", "emulator") or settings.enable_cloud:
            raise ValueError("Local demo cannot connect to a cloud runtime")
        runtime = build_runtime(settings)
    dispatcher = LocalDispatcher(runtime)
    app = create_app(runtime)
    api_lifespan = app.router.lifespan_context

    async def deliver():
        while True:
            await dispatcher.tick()
            await asyncio.sleep(0.25)

    @asynccontextmanager
    async def lifespan(app):
        async with api_lifespan(app):
            task = asyncio.create_task(deliver())
            try:
                yield
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app.router.lifespan_context = lifespan
    return app
