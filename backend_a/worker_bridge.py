"""A-side implementations of B's unchanged JobIO/JobSink protocols.

The actual worker.handler.handle_job -> worker.jobs.run_job pipeline runs here.
Result commit and progression are separate transactions with a durable recovery
checkpoint. A redelivery resumes progression without calling AI again.
"""

import asyncio
import logging
import math
import re
from datetime import timedelta

from backend_a.game import root
from backend_a.tasks import dispatch_outbox
from common.enums import AssetKind, ErrorCode, JobKind
from common.models import ErrorInfo, GestureBatch, JobPayload, JobResult
from worker.ai.base import AIError
from worker.handler import handle_job
from worker.odai import FileOdaiSource

logger = logging.getLogger(__name__)


def _matches(job, p):
    return bool(
        job
        and job["kind"] == p.kind
        and job["revision"] == p.revision
        and job.get("step_index", p.step_index) == p.step_index
    )


def _eligible(tx, p):
    base = root(p.room_id, p.round_id)
    room, rd, private = tx.get(f"rooms/{p.room_id}"), tx.get(base), tx.get(f"{base}/private/main")
    if not room or not rd or not private or room.get("current_round_id") != p.round_id:
        return False
    if set(private["returned_uids"]) == set(private["players"]):
        return False
    if p.kind == JobKind.gesture_read:
        return p.step_index == 2 and rd["status"] in ("playing", "finished", "failed")
    return (
        rd["status"] == "playing"
        and rd["revision"] == p.revision
        and rd["current_step_index"] == (5 if p.kind == JobKind.similarity else p.step_index)
    )


class GameJobIO:
    """Read A's private documents; never expose gesture recordings to AI."""

    def __init__(self, game, odai_source=None):
        self.game = game
        self.odai_source = odai_source or FileOdaiSource()
        self.created_assets = []

    def _private(self, p):
        def read(tx):
            if not _eligible(tx, p):
                raise AIError(ErrorCode.invalid_input, "処理対象のラウンドではありません", False)
            return tx.get(f"{root(p.room_id, p.round_id)}/private/main")

        return self.game.store.atomic(read)

    async def load_odai(self, p):
        private = self._private(p)
        if private.get("odai_text") is not None:
            return private["odai_text"]
        # B's real FileOdaiSource selects; this adapter only persists the choice.
        chosen = self.odai_source.select()

        def save(tx):
            if not _eligible(tx, p):
                raise AIError(ErrorCode.invalid_input, "ラウンドが終了しました", False)
            path = f"{root(p.room_id, p.round_id)}/private/main"
            current = tx.get(path)
            if current.get("odai_text") is None:
                current["odai_text"] = chosen.text
                tx.set(path, current)
            return current["odai_text"]

        return self.game.store.atomic(save)

    async def load_text(self, p):
        if p.step_index == 0:
            return None
        private = self._private(p)
        return private["outputs"][str(p.step_index - 1)]["text"]

    async def load_image(self, p):
        private = self._private(p)
        asset_id = private["outputs"]["4"]["asset_id"]
        doc = self.game.store.atomic(
            lambda tx: tx.get(f"{root(p.room_id, p.round_id)}/assets/{asset_id}")
        )
        if not doc or doc["kind"] != AssetKind.image:
            raise AIError(ErrorCode.invalid_input, "最終画像が見つかりません", False)
        return self.game.storage.blobs.get(doc["path"])

    async def load_batches(self, p):
        private = self._private(p)
        docs = self.game.store.atomic(
            lambda tx: tx.list(f"{root(p.room_id, p.round_id)}/gesture_batches")
        )
        session = private["gesture"]["session_id"]
        return [
            GestureBatch.model_validate(doc)
            for _, doc in sorted(docs, key=lambda item: int(item[0]))
            if doc["gesture_session_id"] == session
        ]

    async def load_conclusion(self, p):
        return self._private(p)["outputs"]["5"]["text"]

    async def save_image(self, p, data):
        self._private(p)
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise AIError(ErrorCode.ai_bad_output, "PNG画像が必要です", True)
        asset_id = self.game.storage.save_asset(
            p.room_id, p.round_id, AssetKind.image, p.step_index, data, "image/png"
        )
        self.created_assets.append(asset_id)
        return asset_id

    def discard_uncommitted(self, p):
        for asset_id in self.created_assets:
            private = self.game.store.atomic(
                lambda tx: tx.get(f"{root(p.room_id, p.round_id)}/private/main")
            )
            if private and any(
                out.get("asset_id") == asset_id for out in private["outputs"].values()
            ):
                continue
            self.game._discard_asset(p.room_id, p.round_id, asset_id)


class RetryableWrite(Exception):
    pass


class GameJobSink:
    """Persist a B JobResult, then resume A progress through the existing callback."""

    def __init__(self, game, payload, attempt, advance):
        self.game, self.payload, self.attempt, self.advance = game, payload, attempt, advance
        self.should_advance = False

    def _validate(self, tx, p, result):
        if not result.ok and result.error:
            return result
        valid = result.ok and result.error is None
        if p.kind == JobKind.image_gen:
            asset = (
                tx.get(f"{root(p.room_id, p.round_id)}/assets/{result.asset_id}")
                if result.asset_id and re.fullmatch(r"[0-9a-f]{32}", result.asset_id)
                else None
            )
            valid = valid and bool(
                asset and asset["kind"] == "image" and asset["step_index"] == p.step_index
            )
        elif p.kind in (JobKind.conclude, JobKind.gesture_read):
            valid = valid and bool(result.text and result.text.strip())
        else:
            valid = (
                valid
                and result.score is not None
                and math.isfinite(result.score)
                and -1.000000001 <= result.score <= 1.000000001
            )
        if valid:
            return result
        return JobResult(
            ok=False,
            error=ErrorInfo(
                code=ErrorCode.ai_bad_output,
                message="AIの結果の形式を確認できませんでした",
                retryable=True,
            ),
        )

    async def write_job_result(self, p: JobPayload, result: JobResult, *, final: bool) -> None:
        if p != self.payload or not final:
            raise ValueError("Only a final result for the dispatched payload can be committed")
        base = root(p.room_id, p.round_id)

        def write(tx):
            path = f"{base}/jobs/{p.job_id}"
            job = tx.get(path)
            if not _matches(job, p) or job["attempt"] != self.attempt:
                return "ignored"
            if job["status"] in ("done", "failed"):
                return "advance" if job.get("advance_pending") else "ignored"
            if not _eligible(tx, p):
                return "ignored"
            normalized = self._validate(tx, p, result)
            job["last_error"] = normalized.error.model_dump() if normalized.error else None
            if (
                not normalized.ok
                and normalized.error.retryable
                and self.attempt < job["max_attempts"]
            ):
                job["status"] = "pending"
                tx.set(path, job)
                return "retry"
            rd, private = tx.get(base), tx.get(f"{base}/private/main")
            job.update(
                status="done" if normalized.ok else "failed",
                result=normalized.model_dump(),
                finalized_at=self.game.clock(),
                advance_pending=normalized.ok and p.kind != JobKind.gesture_read,
            )
            tx.set(path, job)
            if job["advance_pending"]:
                tx.set(
                    f"progress_outbox/{p.round_id}-{p.job_id}",
                    {"payload": p.model_dump(mode="json"), "created_at": self.game.clock()},
                )
            if p.kind == JobKind.gesture_read:
                rd["gesture_ai_status"] = "done" if normalized.ok else "failed"
                if normalized.ok:
                    private["gesture_ai_text"] = normalized.text
                    final_doc = tx.get(f"{base}/result/final")
                    if final_doc:
                        final_doc["gesture_ai_text"] = normalized.text
                        tx.set(f"{base}/result/final", final_doc)
                tx.set(base, rd)
            elif not normalized.ok:
                if p.step_index is not None:
                    step = tx.get(f"{base}/steps/{p.step_index}")
                    step["status"] = "failed"
                    tx.set(f"{base}/steps/{p.step_index}", step)
                rd["result_status"] = "failed"
                room = tx.get(f"rooms/{p.room_id}")
                self.game._fail(tx, p.room_id, base, room, rd, private, "ai_failed")
            elif p.kind == JobKind.similarity:
                rd["result_status"] = "ready"
                score = max(-1.0, min(1.0, normalized.score))
                tx.set(
                    f"{base}/result/final",
                    {
                        "odai": private["odai_text"],
                        "final_image_asset_id": private["outputs"]["4"]["asset_id"],
                        "ai_conclusion": private["outputs"]["5"]["text"],
                        "similarity": score,
                        "gesture_ai_text": private.get("gesture_ai_text"),
                    },
                )
                tx.set(base, rd)
            else:
                private["outputs"][str(p.step_index)] = {
                    "text": normalized.text,
                    "asset_id": normalized.asset_id,
                }
                step = tx.get(f"{base}/steps/{p.step_index}")
                step["status"] = "done"
                tx.set(f"{base}/steps/{p.step_index}", step)
            tx.set(f"{base}/private/main", private)
            return "advance" if job["advance_pending"] else "ignored"

        outcome = self.game.store.atomic(write)
        self.should_advance = outcome == "advance"
        if outcome == "retry":
            raise RetryableWrite("Invalid output will be retried")

    async def advance_step(self, room_id: str, round_id: str) -> None:
        p = self.payload
        if (room_id, round_id) != (p.room_id, p.round_id):
            raise ValueError("Wrong round for progress callback")
        if not self.should_advance:
            return
        self.advance(room_id, round_id)  # A's existing synchronous shared entry point.

        self.game.acknowledge_job_progress(p)


class WorkerBridge:
    """Local/private-service composition; never instantiate a real AI client here.

    retry_count corresponds to Cloud Tasks TaskRetryCount. It is a delivery hint,
    not authorization. A private receiver must authenticate the Tasks identity.
    """

    def __init__(self, game, ai, *, advance=None, odai_source=None):
        self.game, self.ai = game, ai
        self.advance = advance or game.advance_step
        self.odai_source = odai_source

    def _prepare(self, p, retry_count):
        def claim(tx):
            path = f"{root(p.room_id, p.round_id)}/jobs/{p.job_id}"
            job = tx.get(path)
            if not _matches(job, p):
                return "ignored", 0
            if job["status"] == "done":
                room = tx.get(f"rooms/{p.room_id}")
                return (
                    "recover"
                    if job.get("advance_pending")
                    and room
                    and room.get("current_round_id") == p.round_id
                    else "ignored"
                ), job["attempt"]
            if job["status"] == "failed" or not _eligible(tx, p):
                return "ignored", job["attempt"]
            if job["status"] == "processing" and retry_count < job["attempt"]:
                return "inflight", job["attempt"]
            if job["attempt"] >= job["max_attempts"]:
                return "exhausted", job["attempt"]
            job.update(
                status="processing",
                attempt=min(job["max_attempts"], max(job["attempt"] + 1, retry_count + 1)),
            )
            tx.set(path, job)
            tx.set(
                f"execution_outbox/{p.round_id}-{p.job_id}",
                {
                    "payload": p.model_dump(mode="json"),
                    "attempt": job["attempt"],
                    "expires_at": self.game.clock()
                    + timedelta(seconds=self.game.settings.ai_timeout_s),
                },
            )
            if p.kind == JobKind.gesture_read:
                base = root(p.room_id, p.round_id)
                rd = tx.get(base)
                rd["gesture_ai_status"] = "processing"
                tx.set(base, rd)
            return "run", job["attempt"]

        return self.game.store.atomic(claim)

    def _retry(self, p, attempt):
        def update(tx):
            path = f"{root(p.room_id, p.round_id)}/jobs/{p.job_id}"
            job = tx.get(path)
            if _matches(job, p) and job["attempt"] == attempt and job["status"] == "processing":
                job["status"] = "pending"
                job["last_error"] = (
                    job.get("last_error")
                    or ErrorInfo(
                        code=ErrorCode.ai_failed, message="処理を再試行します", retryable=True
                    ).model_dump()
                )
                tx.set(path, job)

        self.game.store.atomic(update)

    async def handle(self, payload: JobPayload, retry_count=0) -> int:
        p = payload
        if retry_count < 0 or not all(
            re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value)
            for value in (p.room_id, p.round_id, p.job_id)
        ):
            raise ValueError("Invalid task identifiers or retry count")
        expected = {
            JobKind.image_gen: {0, 4},
            JobKind.gesture_read: {2},
            JobKind.conclude: {5},
            JobKind.similarity: {None},
        }
        if p.step_index not in expected[p.kind]:
            raise ValueError("Job kind and step index disagree")
        action, attempt = self._prepare(p, retry_count)
        if action == "ignored":
            return 200
        if action == "inflight":
            return 500
        sink = GameJobSink(self.game, p, attempt, self.advance)
        io = GameJobIO(self.game, self.odai_source)
        try:
            if action == "recover":
                sink.should_advance = True
                await sink.advance_step(p.room_id, p.round_id)
                return 200
            if action == "exhausted":
                await sink.write_job_result(
                    p,
                    JobResult(
                        ok=False,
                        error=ErrorInfo(
                            code=ErrorCode.ai_timeout,
                            message="処理を完了できませんでした",
                            retryable=False,
                        ),
                    ),
                    final=True,
                )
                return 200
            status = await asyncio.wait_for(
                handle_job(p, attempt, ai=self.ai, io=io, sink=sink),
                timeout=self.game.settings.ai_timeout_s,
            )
            if status == 500:
                self._retry(p, attempt)
            return status
        except TimeoutError:
            if action == "run" and attempt >= 3:
                await sink.write_job_result(
                    p,
                    JobResult(
                        ok=False,
                        error=ErrorInfo(
                            code=ErrorCode.ai_timeout,
                            message="処理を完了できませんでした",
                            retryable=False,
                        ),
                    ),
                    final=True,
                )
                return 200
            self._retry(p, attempt)
            return 500
        except Exception:
            logger.exception("Worker delivery will be retried", extra={"job_id": p.job_id})
            self._retry(p, attempt)
            return 500
        finally:
            try:
                io.discard_uncommitted(p)
            except Exception:
                logger.exception("Uncommitted image cleanup deferred")
            dispatch_outbox(self.game.store, self.game.tasks)
