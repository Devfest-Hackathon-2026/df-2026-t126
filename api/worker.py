"""Persistent private Worker composition; B's AI and handler remain unchanged."""

from api.worker_app import create_worker_app
from backend_a.runtime import build_runtime
from common.settings import Settings
from worker.ai.mock import MockAIClient


def build_worker_app(settings=None):
    settings = settings or Settings()
    runtime = build_runtime(settings)
    if settings.ai_mode == "real":
        from worker.ai.real import RealAIClient

        ai = RealAIClient(settings)
    else:
        ai = MockAIClient(delay_s=settings.mock_delay_s)
    return create_worker_app(runtime, ai)


app = build_worker_app()
