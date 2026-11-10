import pytest
from fastapi.testclient import TestClient

from common.enums import ErrorCode, JobKind
from common.models import JobPayload
from worker.ai.base import AIError, cosine
from worker.ai.mock import MockAIClient
from worker.handler import handle_job
from worker.io_memory import MemoryJobIO
from worker.jobs import run_job
from worker.main import app
from worker.odai import FileOdaiSource
from worker.prompts import PROMPTS, build_image_prompt


def payload(kind: JobKind) -> JobPayload:
    return JobPayload(job_id="j1", kind=kind, room_id="r", round_id="rd", step_index=1, revision=1)


class Sink:
    def __init__(self):
        self.written, self.advanced = [], 0

    async def write_job_result(self, p, result, *, final):
        self.written.append(result)

    async def advance_step(self, room_id, round_id):
        self.advanced += 1


class FailingAI(MockAIClient):
    def __init__(self, err):
        super().__init__()
        self.err = err

    async def generate_image(self, prompt):
        raise self.err


async def test_image_gen_saves_asset():
    io = MemoryJobIO(text=None)
    r = await run_job(payload(JobKind.image_gen), ai=MockAIClient(), io=io)
    assert r.ok and r.asset_id in io.saved


async def test_all_kinds_ok():
    io = MemoryJobIO()
    for k in (JobKind.gesture_read, JobKind.conclude, JobKind.similarity):
        assert (await run_job(payload(k), ai=MockAIClient(), io=io)).ok
    r = await run_job(payload(JobKind.similarity), ai=MockAIClient(), io=io)
    assert r.score == pytest.approx(1.0)  # お題と結論が同じ文字列


async def test_retryable_returns_500_until_max():
    ai = FailingAI(AIError(ErrorCode.ai_timeout, "x", True))
    sink = Sink()
    assert (
        await handle_job(payload(JobKind.image_gen), 1, ai=ai, io=MemoryJobIO(), sink=sink) == 500
    )
    assert sink.written == []
    assert (
        await handle_job(payload(JobKind.image_gen), 3, ai=ai, io=MemoryJobIO(), sink=sink) == 200
    )
    assert sink.written[0].ok is False and sink.advanced == 0


async def test_non_retryable_is_final_immediately():
    ai = FailingAI(AIError(ErrorCode.ai_blocked, "x", False))
    sink = Sink()
    assert (
        await handle_job(payload(JobKind.image_gen), 1, ai=ai, io=MemoryJobIO(), sink=sink) == 200
    )
    assert sink.written[0].error.code == ErrorCode.ai_blocked


async def test_success_advances():
    sink = Sink()
    assert (
        await handle_job(
            payload(JobKind.conclude), 1, ai=MockAIClient(), io=MemoryJobIO(), sink=sink
        )
        == 200
    )
    assert sink.advanced == 1


def test_empty_text_uses_empty_prompt():
    assert build_image_prompt("   ") == PROMPTS.image_from_empty
    assert "ねこ" in build_image_prompt("ねこ")


def test_cosine_and_odai():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert FileOdaiSource().select().text


def test_http_entry():
    c = TestClient(app)
    body = {
        "job_id": "j",
        "kind": "conclude",
        "room_id": "r",
        "round_id": "rd",
        "step_index": 1,
        "revision": 1,
    }
    r = c.post("/tasks/run", json=body)
    assert r.status_code == 200
    assert c.get("/health").json() == {"ok": True}
