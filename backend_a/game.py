"""All gameplay changes are serialized through document transactions.

The public round/step documents contain state only. Input, outputs, returned
players and session bookkeeping live in private/main (server-only).
"""

import hashlib
import json
import logging
import secrets
import string
from datetime import UTC, datetime, timedelta

from backend_a.errors import ApiError, require
from backend_a.tasks import dispatch_outbox
from common.enums import AssetKind, ErrorCode
from common.models import JOB_POLICY, ErrorInfo, GameConfig, JobPayload, JobResult

logger = logging.getLogger(__name__)


def new_id():
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(20))


def root(room_id, round_id):
    return f"rooms/{room_id}/rounds/{round_id}"


class GameService:
    def __init__(self, store, storage, tasks, settings, clock=None, odai_source=None):
        self.store, self.storage, self.tasks, self.settings = store, storage, tasks, settings
        self.clock = clock or (lambda: datetime.now(UTC))
        self.odai_source = odai_source  # B's OdaiSource; never implement AI/odai selection here.

    def _command(self, uid, action, request_id, body, callback):
        key = hashlib.sha256(f"{uid}:{action}:{request_id}".encode()).hexdigest()
        fingerprint = hashlib.sha256(
            json.dumps(body, sort_keys=True, default=str).encode()
        ).hexdigest()

        def work(tx):
            previous = tx.get(f"requests/{key}")
            if previous:
                require(
                    previous["fingerprint"] == fingerprint,
                    "INVALID_INPUT",
                    400,
                    "同じ送信IDで内容を変更できません",
                )
                return previous["response"]
            result = callback(tx)
            tx.set(
                f"requests/{key}",
                {"fingerprint": fingerprint, "response": result, "created_at": self.clock()},
            )
            return result

        result = self.store.atomic(work)
        dispatch_outbox(self.store, self.tasks)
        return result

    def _room(self, tx, room_id, uid=None):
        room = tx.get(f"rooms/{room_id}")
        require(room is not None, "ROOM_NOT_FOUND", 404, "部屋が見つかりません")
        if uid is not None:
            player = tx.get(f"rooms/{room_id}/players/{uid}")
            require(player is not None, "NOT_YOUR_TURN", 403, "この部屋に参加していません")
            return room, player
        return room

    def _round(self, tx, round_id, uid=None):
        lookup = tx.get(f"round_lookup/{round_id}")
        require(lookup is not None, "ROOM_NOT_FOUND", 404, "ラウンドが見つかりません")
        room_id = lookup["room_id"]
        base = root(room_id, round_id)
        room = self._room(tx, room_id)
        rd = tx.get(base)
        private = tx.get(f"{base}/private/main")
        if uid is not None:
            require(uid in private["players"], "NOT_YOUR_TURN", 403, "参加者ではありません")
        return room_id, base, room, rd, private

    def _player(self, name):
        now = self.clock()
        return {
            "name": name,
            "role": None,
            "consented_at": now,
            "last_seen_at": now,
            "phase": "lobby",
        }

    def _limit_room_action(self, tx, uid, action, uid_limit, global_limit):
        now = self.clock()
        scope = hashlib.sha256(uid.encode()).hexdigest()
        limits = [(scope, uid_limit)]
        if global_limit:
            limits.insert(0, ("all", global_limit))
        for scope, limit in limits:
            path = f"room_action_limits/{action}-{scope}"
            doc = tx.get(path)
            if doc is None or now >= doc["expires_at"]:
                doc = {"count": 0, "expires_at": now + timedelta(seconds=60)}
            require(
                doc["count"] < limit,
                "TOO_MANY_ATTEMPTS",
                429,
                "少し待ってからもう一度お試しください",
            )
            doc["count"] += 1
            tx.set(path, doc)

    def create_room(self, uid, body):
        require(body["consented"], "CONSENT_REQUIRED", 403, "同意が必要です")
        room_id = new_id()

        def work(tx):
            self._limit_room_action(
                tx,
                uid,
                "create",
                self.settings.room_create_uid_limit,
                self.settings.room_create_global_limit,
            )
            for _ in range(50):
                code = f"{secrets.randbelow(10000):04d}"
                if tx.get(f"join_codes/{code}") is None:
                    break
            else:
                raise ApiError("INTERNAL", 500, "部屋を作成できませんでした")
            tx.set(
                f"rooms/{room_id}",
                {
                    "status": "waiting",
                    "fail_reason": None,
                    "join_code": code,
                    "host_player_id": uid,
                    "created_at": self.clock(),
                    "current_round_id": None,
                },
            )
            tx.set(f"rooms/{room_id}/players/{uid}", self._player(body["name"]))
            tx.set(f"join_codes/{code}", {"room_id": room_id})
            return {"room_id": room_id, "join_code": code, "player_id": uid}

        return self._command(uid, "create", body["request_id"], body, work)

    def join_room(self, uid, body):
        require(body["consented"], "CONSENT_REQUIRED", 403, "同意が必要です")
        replay_key = hashlib.sha256(f"{uid}:join:{body['request_id']}".encode()).hexdigest()
        if self.store.atomic(lambda tx: tx.get(f"requests/{replay_key}")):
            return self._command(uid, "join", body["request_id"], body, lambda tx: None)

        # Persist rate limits even when the subsequent room lookup fails.
        def rate_limit(tx):
            path = f"join_attempts/{uid}"
            doc = tx.get(path) or {"since": self.clock(), "count": 0}
            if (self.clock() - doc["since"]).total_seconds() >= self.settings.join_attempt_window_s:
                doc = {"since": self.clock(), "count": 0}
            require(
                doc["count"] < self.settings.join_attempt_limit,
                "TOO_MANY_ATTEMPTS",
                429,
                "少し待ってからもう一度お試しください",
            )
            doc["count"] += 1
            tx.set(path, doc)

        self.store.atomic(rate_limit)

        def work(tx):
            code = tx.get(f"join_codes/{body['join_code']}")
            require(code is not None, "ROOM_NOT_FOUND", 404, "部屋が見つかりません")
            room_id = code["room_id"]
            room = self._room(tx, room_id)
            require(room["status"] == "waiting", "INVALID_STATE")
            players = tx.list(f"rooms/{room_id}/players")
            if not any(key == uid for key, _ in players):
                require(len(players) < 3, "ROOM_FULL")
                tx.set(f"rooms/{room_id}/players/{uid}", self._player(body["name"]))
                if not players:  # 全員が出て空になった部屋: 入った人がホストになる
                    room["host_player_id"] = uid
                    tx.set(f"rooms/{room_id}", room)
            return {"room_id": room_id, "player_id": uid}

        return self._command(uid, "join", body["request_id"], body, work)

    def select_role(self, uid, room_id, body):
        def work(tx):
            room, player = self._room(tx, room_id, uid)
            require(room["status"] == "waiting", "INVALID_STATE")
            role = body["role"]
            players = tx.list(f"rooms/{room_id}/players")
            require(
                role is None or not any(key != uid and p["role"] == role for key, p in players),
                "ROLE_TAKEN",
            )
            player["role"] = role
            tx.set(f"rooms/{room_id}/players/{uid}", player)
            return {"accepted": True}

        return self._command(uid, f"role/{room_id}", body["request_id"], body, work)

    def _queue(self, tx, task_id, target, payload, at=None):
        tx.set(
            f"task_outbox/{task_id}",
            {"target": target, "payload": payload, "schedule_at": at, "sent": False},
        )

    def _job(self, tx, base, room_id, round_id, rd, kind, index):
        # Deterministic names provide idempotency across transaction retries.
        job_id = f"{kind}-{index if index is not None else 'result'}-{rd['revision']}"
        path = f"{base}/jobs/{job_id}"
        if tx.get(path):
            return
        payload = JobPayload(
            job_id=job_id,
            kind=kind,
            room_id=room_id,
            round_id=round_id,
            step_index=index,
            revision=rd["revision"],
        )
        tx.set(
            path,
            {
                "kind": kind,
                "step_index": index,
                "status": "pending",
                "attempt": 0,
                "max_attempts": 3,
                "last_error": None,
                "revision": rd["revision"],
            },
        )
        self._queue(tx, f"job-{round_id}-{job_id}", "worker", payload.model_dump(mode="json"))

    def start(self, uid, room_id, body):
        round_id = new_id()
        replay_key = hashlib.sha256(
            f"{uid}:start/{room_id}:{body['request_id']}".encode()
        ).hexdigest()
        if self.store.atomic(lambda tx: tx.get(f"requests/{replay_key}")):
            result = self._command(
                uid, f"start/{room_id}", body["request_id"], body, lambda tx: None
            )
            self.cleanup()
            return result

        def preflight(tx):
            room, _ = self._room(tx, room_id, uid)
            require(room["host_player_id"] == uid, "NOT_HOST", 403, "ホストのみ開始できます")
            require(room["status"] == "waiting", "INVALID_STATE")
            players = tx.list(f"rooms/{room_id}/players")
            require(
                len(players) == 3 and {p["role"] for _, p in players} == {"A", "B", "C"},
                "ROLES_NOT_READY",
            )

        self.store.atomic(preflight)
        # B chooses the odai. Local API without B records no invented production odai.
        selected = self.odai_source.select() if self.odai_source else None

        def work(tx):
            room, _ = self._room(tx, room_id, uid)
            require(room["host_player_id"] == uid, "NOT_HOST", 403, "ホストのみ開始できます")
            require(room["status"] == "waiting", "INVALID_STATE")
            players = tx.list(f"rooms/{room_id}/players")
            require(
                len(players) == 3 and {p["role"] for _, p in players} == {"A", "B", "C"},
                "ROLES_NOT_READY",
            )
            require(all(p["consented_at"] for _, p in players), "CONSENT_REQUIRED", 403)
            config_doc = tx.get("config/game")
            require(
                config_doc is not None or self.settings.runtime_mode != "cloud",
                "INVALID_STATE",
                409,
                "ゲームの時間設定が必要です",
            )
            config = GameConfig.model_validate(config_doc or {})
            self._limit_room_action(
                tx,
                uid,
                "start",
                self.settings.round_start_uid_limit,
                self.settings.round_start_global_limit,
            )
            base = root(room_id, round_id)
            rd = {
                "status": "playing",
                "current_step_index": 0,
                "revision": 0,
                "gesture_ai_status": "pending",
                "result_status": "pending",
            }
            private = {
                "players": {key: p["role"] for key, p in players},
                "returned_uids": [],
                "outputs": {},
                "odai_text": selected.text if selected else None,
                "config": config.model_dump(),
                "gesture": None,
            }
            for index, (kind, role) in enumerate(
                [
                    ("image_gen", None),
                    ("text", "A"),
                    ("gesture", "B"),
                    ("text", "C"),
                    ("image_gen", None),
                    ("conclude", None),
                ]
            ):
                actor_id = next((key for key, p in players if p["role"] == role), None)
                tx.set(
                    f"{base}/steps/{index}",
                    {
                        "step_index": index,
                        "type": kind,
                        "actor": "player" if role else "ai",
                        "player_id": actor_id,
                        "role": role,
                        "status": "processing"
                        if index == 0
                        else ("waiting" if role else "pending"),
                        "started_at": self.clock() if index == 0 else None,
                        "deadline_at": None,
                        "timed_out": False,
                    },
                )
            tx.set(base, rd)
            tx.set(f"{base}/private/main", private)
            tx.set(f"round_lookup/{round_id}", {"room_id": room_id})
            previous_round = room.get("current_round_id")
            if previous_round:
                tx.set(
                    f"cleanup_outbox/{room_id}-{previous_round}",
                    {"room_id": room_id, "round_id": previous_round},
                )
            room.update(status="playing", current_round_id=round_id, fail_reason=None)
            tx.set(f"rooms/{room_id}", room)
            for key, p in players:
                p.update(phase="playing", last_seen_at=self.clock())
                tx.set(f"rooms/{room_id}/players/{key}", p)
            self._job(tx, base, room_id, round_id, rd, "image_gen", 0)
            self._watchdog(tx, room_id, round_id)
            return {"accepted": True, "round_id": round_id}

        result = self._command(uid, f"start/{room_id}", body["request_id"], body, work)
        self.cleanup()
        return result

    def _watchdog(self, tx, room_id, round_id):
        due = self.clock() + timedelta(
            seconds=min(self.settings.heartbeat_interval_s, self.settings.dropout_after_s)
        )
        task_id = hashlib.sha256(f"{round_id}:watchdog:{due.isoformat()}".encode()).hexdigest()
        self._queue(
            tx,
            task_id,
            "deadline",
            {"room_id": room_id, "round_id": round_id, "kind": "watchdog", "check_id": task_id},
            due,
        )

    def _active(self, tx, uid, round_id, index=None, kind=None):
        room_id, base, room, rd, private = self._round(tx, round_id, uid)
        require(uid not in private["returned_uids"], "NOT_YOUR_TURN", 403)
        require(room["current_round_id"] == round_id and rd["status"] == "playing", "INVALID_STATE")
        step_index = rd["current_step_index"] if index is None else index
        step = tx.get(f"{base}/steps/{step_index}")
        require(
            step is not None
            and step["player_id"] == uid
            and (kind is None or step["type"] == kind),
            "NOT_YOUR_TURN",
            403,
            "あなたの番ではありません",
        )
        require(step["status"] == "active", "ALREADY_SUBMITTED")
        require(
            self.clock() <= step["deadline_at"] + timedelta(seconds=self.settings.deadline_grace_s),
            "DEADLINE_PASSED",
        )
        return room_id, base, room, rd, private, step

    def _activate(self, tx, room_id, round_id, base, rd, private, index):
        step = tx.get(f"{base}/steps/{index}")
        if step["status"] not in ("waiting", "pending"):
            return
        rd["current_step_index"] = index
        rd["revision"] += 1
        step["started_at"] = self.clock()
        if step["actor"] == "player":
            config = private["config"]
            seconds = (
                config["countdown_seconds"] + config["record_seconds"]
                if step["type"] == "gesture"
                else config["text_seconds"]
            )
            step.update(status="active", deadline_at=self.clock() + timedelta(seconds=seconds))
            due = step["deadline_at"] + timedelta(seconds=self.settings.deadline_grace_s)
            self._queue(
                tx,
                f"deadline-{round_id}-{index}-{rd['revision']}",
                "deadline",
                {
                    "room_id": room_id,
                    "round_id": round_id,
                    "kind": "step",
                    "step_index": index,
                    "revision": rd["revision"],
                },
                due,
            )
        else:
            step["status"] = "processing"
            self._job(tx, base, room_id, round_id, rd, step["type"], index)
        tx.set(f"{base}/steps/{index}", step)
        tx.set(base, rd)

    def _advance(self, tx, room_id, round_id, base, room, rd, private):
        if room["current_round_id"] != round_id or rd["status"] != "playing":
            return
        index = rd["current_step_index"]
        step = tx.get(f"{base}/steps/{index}")
        if step["status"] not in ("done", "timeout"):
            return
        if step["type"] == "image_gen":
            output = private["outputs"].get(str(index), {})
            asset_id = output.get("asset_id")
            require(asset_id and tx.get(f"{base}/assets/{asset_id}"), "INVALID_STATE")
        if index == 2:
            gesture = private.get("gesture") or {}
            require(gesture.get("finished") and gesture.get("video_asset_id"), "INVALID_STATE")
            asset = tx.get(f"{base}/assets/{gesture['video_asset_id']}")
            require(asset is not None, "INVALID_STATE")
        if index < 5:
            self._activate(tx, room_id, round_id, base, rd, private, index + 1)
        elif rd["result_status"] == "pending":
            rd["result_status"] = "processing"
            rd["revision"] += 1
            self._job(tx, base, room_id, round_id, rd, "similarity", None)
            tx.set(base, rd)
        elif rd["result_status"] == "ready":
            rd["status"] = room["status"] = "finished"
            tx.set(base, rd)
            tx.set(f"rooms/{room_id}", room)
            for uid in private["players"]:
                p = tx.get(f"rooms/{room_id}/players/{uid}")
                p["phase"] = "viewing"
                tx.set(f"rooms/{room_id}/players/{uid}", p)

    def advance_step(self, room_id: str, round_id: str) -> None:
        """Shared A entry point called by API and B after B commits a result.

        Repeated calls are harmless. B must persist the complete output/asset,
        matching job status and step status atomically before calling this.
        """

        def work(tx):
            actual, base, room, rd, private = self._round(tx, round_id)
            require(actual == room_id, "INVALID_INPUT", 400)
            self._advance(tx, room_id, round_id, base, room, rd, private)

        self.store.atomic(work)
        dispatch_outbox(self.store, self.tasks)

    def acknowledge_job_progress(self, payload: JobPayload):
        """Only clear a checkpoint after the progress transaction returned."""
        p = payload

        def ack(tx):
            path = f"{root(p.room_id, p.round_id)}/jobs/{p.job_id}"
            job = tx.get(path)
            if (
                job
                and job["kind"] == p.kind
                and job["revision"] == p.revision
                and job["status"] == "done"
            ):
                job["advance_pending"] = False
                tx.set(path, job)
            tx.delete(f"progress_outbox/{p.round_id}-{p.job_id}")

        self.store.atomic(ack)

    def recover_job_progress(self):
        """Recover committed results even if the AI task exhausted its retries.

        Run from A's maintenance; never call an AI client.
        Failures leave the durable outbox intact for the next invocation.
        """
        try:
            pending = self.store.atomic(lambda tx: tx.list("progress_outbox"))
        except Exception:
            logger.exception("Progress outbox unavailable; retry later")
            return
        for _, doc in pending:
            try:
                p = JobPayload.model_validate(doc["payload"])
                job = self.store.atomic(
                    lambda tx, p=p: tx.get(f"{root(p.room_id, p.round_id)}/jobs/{p.job_id}")
                )
                if (
                    job
                    and job["status"] == "done"
                    and job["revision"] == p.revision
                    and job["kind"] == p.kind
                    and job.get("advance_pending")
                ):
                    self.advance_step(p.room_id, p.round_id)
                self.acknowledge_job_progress(p)
            except Exception:
                logger.exception("Committed result progress remains queued")

    def recover_job_execution(self):
        """Retry abandoned inference receipts or finalize the exhausted third try.

        This is a persisted timeout check, not an AI call. A fresh task name can
        recover a receipt whose Cloud Tasks delivery budget has already ended.
        """
        try:
            pending = self.store.atomic(lambda tx: tx.list("execution_outbox"))
        except Exception:
            logger.exception("Execution outbox unavailable; retry later")
            return
        for key, _ in pending:

            def recover(tx, key=key):
                path = f"execution_outbox/{key}"
                receipt = tx.get(path)
                if not receipt:
                    return
                p = JobPayload.model_validate(receipt["payload"])
                base = root(p.room_id, p.round_id)
                job_path = f"{base}/jobs/{p.job_id}"
                job, room, rd = tx.get(job_path), tx.get(f"rooms/{p.room_id}"), tx.get(base)
                private = tx.get(f"{base}/private/main")
                active = (
                    job
                    and room
                    and rd
                    and private
                    and job["kind"] == p.kind
                    and job["revision"] == p.revision
                    and job["attempt"] == receipt["attempt"]
                    and room.get("current_round_id") == p.round_id
                    and set(private["returned_uids"]) != set(private["players"])
                )
                if (
                    not active
                    or job["status"] in ("done", "failed")
                    or (
                        p.kind != "gesture_read"
                        and (rd["status"] != "playing" or rd["revision"] != p.revision)
                    )
                ):
                    tx.delete(path)
                    return
                if self.clock() < receipt["expires_at"]:
                    return
                error = ErrorInfo(
                    code=ErrorCode.ai_timeout,
                    message="処理を完了できませんでした",
                    retryable=job["attempt"] < job["max_attempts"],
                )
                job["last_error"] = error.model_dump()
                if error.retryable:
                    job["status"] = "pending"
                    self._queue(
                        tx,
                        f"recover-{p.round_id}-{p.job_id}-{job['attempt']}",
                        "worker",
                        p.model_dump(mode="json"),
                    )
                else:
                    job.update(
                        status="failed",
                        result=JobResult(ok=False, error=error).model_dump(),
                        advance_pending=False,
                        finalized_at=self.clock(),
                    )
                    if not JOB_POLICY[p.kind].fatal:
                        rd["gesture_ai_status"] = "failed"
                        tx.set(base, rd)
                    else:
                        if p.step_index is not None:
                            step = tx.get(f"{base}/steps/{p.step_index}")
                            step["status"] = "failed"
                            tx.set(f"{base}/steps/{p.step_index}", step)
                        rd["result_status"] = "failed"
                        self._fail(tx, p.room_id, base, room, rd, private, "ai_failed")
                tx.set(job_path, job)
                tx.delete(path)

            try:
                self.store.atomic(recover)
            except Exception:
                logger.exception("Abandoned job recovery remains queued")
        dispatch_outbox(self.store, self.tasks)

    def submit(self, uid, round_id, index, body):
        require(
            len(body["text"]) <= self.settings.text_max_length,
            "TEXT_TOO_LONG",
            400,
            "文章が長すぎます",
        )

        def work(tx):
            room_id, base, room, rd, private, step = self._active(tx, uid, round_id, index, "text")
            private["outputs"][str(index)] = {"text": body["text"], "asset_id": None}
            step.update(
                status="done",
                timed_out=self.clock() >= step["deadline_at"],
                is_auto=body["is_auto"],
            )
            tx.set(f"{base}/private/main", private)
            tx.set(f"{base}/steps/{index}", step)
            self._advance(tx, room_id, round_id, base, room, rd, private)
            return {"accepted": True}

        return self._command(uid, f"submit/{round_id}/{index}", body["request_id"], body, work)

    def gesture_start(self, uid, round_id, body):
        session_id = new_id()

        def work(tx):
            _, base, _, _, private, step = self._active(tx, uid, round_id, kind="gesture")
            require(private["gesture"] is None, "ALREADY_SUBMITTED")
            private["gesture"] = {
                "session_id": session_id,
                "finished": False,
                "video_asset_id": None,
            }
            tx.set(f"{base}/private/main", private)
            return {
                "gesture_session_id": session_id,
                "deadline_at": step["deadline_at"].isoformat(),
            }

        return self._command(uid, f"gesture/start/{round_id}", body["request_id"], body, work)

    def _session(self, private, session_id):
        require(
            private.get("gesture") is not None and private["gesture"]["session_id"] == session_id,
            "INVALID_STATE",
        )

    def batches(self, uid, round_id, batch):
        require(
            len(json.dumps(batch, separators=(",", ":")).encode())
            <= self.settings.gesture_batch_max_bytes,
            "PAYLOAD_TOO_LARGE",
            400,
            "座標データを小分けにしてください",
        )

        def work(tx):
            _, base, _, _, private, _ = self._active(tx, uid, round_id, kind="gesture")
            self._session(private, batch["gesture_session_id"])
            require(not private["gesture"]["finished"], "ALREADY_SUBMITTED")
            path = f"{base}/gesture_batches/{batch['sequence_number']}"
            if tx.get(path) is None:
                tx.set(path, batch)
            return {"accepted": True}

        return self.store.atomic(work)

    def _finish_gesture(self, tx, room_id, round_id, base, rd, private):
        private["gesture"]["finished"] = True
        # Background job revision is pinned to this job, NOT compared with main
        # round revision: C may advance while the read is still running.
        self._job(tx, base, room_id, round_id, rd, "gesture_read", 2)
        if private["gesture"].get("video_asset_id"):
            private["outputs"]["2"] = {
                "text": None,
                "asset_id": private["gesture"]["video_asset_id"],
            }
            step = tx.get(f"{base}/steps/2")
            step["status"] = "done"
            tx.set(f"{base}/steps/2", step)
        tx.set(f"{base}/private/main", private)

    def gesture_finish(self, uid, round_id, body):
        def work(tx):
            room_id, base, room, rd, private, _ = self._active(tx, uid, round_id, kind="gesture")
            self._session(private, body["gesture_session_id"])
            self._finish_gesture(tx, room_id, round_id, base, rd, private)
            self._advance(tx, room_id, round_id, base, room, rd, private)
            return {"accepted": True}

        return self._command(uid, f"gesture/finish/{round_id}", body["request_id"], body, work)

    def upload_video(self, uid, round_id, body, data, content_type):
        """Do not execute Storage I/O inside a retryable transaction."""
        fingerprint_body = {
            **body,
            "sha256": hashlib.sha256(data).hexdigest(),
            "type": content_type,
        }
        # Check idempotent replay before saving another object.
        action = f"video/{round_id}"
        key = hashlib.sha256(f"{uid}:{action}:{body['request_id']}".encode()).hexdigest()
        prior = self.store.atomic(lambda tx: tx.get(f"requests/{key}"))
        if prior:
            return self._command(uid, action, body["request_id"], fingerprint_body, lambda tx: None)

        def preflight(tx):
            room_id, _, _, _, private, _ = self._active(tx, uid, round_id, kind="gesture")
            self._session(private, body["gesture_session_id"])
            require(not private["gesture"]["video_asset_id"], "ALREADY_SUBMITTED")
            return room_id, private["config"]["record_seconds"]

        room_id, max_seconds = self.store.atomic(preflight)
        from backend_a.video import validate_video

        require(content_type in self.settings.allowed_video_types, "UNSUPPORTED_MEDIA_TYPE", 400)
        validate_video(data, content_type, max_seconds)
        asset_id = self.storage.save_asset(
            room_id, round_id, AssetKind.video, 2, data, content_type
        )

        def work(tx):
            room_id, base, room, rd, private, _ = self._active(tx, uid, round_id, kind="gesture")
            self._session(private, body["gesture_session_id"])
            require(not private["gesture"]["video_asset_id"], "ALREADY_SUBMITTED")
            private["gesture"]["video_asset_id"] = asset_id
            if private["gesture"]["finished"]:
                self._finish_gesture(tx, room_id, round_id, base, rd, private)
            else:
                tx.set(f"{base}/private/main", private)
            self._advance(tx, room_id, round_id, base, room, rd, private)
            return {"accepted": True, "asset_id": asset_id}

        try:
            result = self._command(uid, action, body["request_id"], fingerprint_body, work)
        except Exception:
            self._discard_asset(room_id, round_id, asset_id)
            raise
        if result["asset_id"] != asset_id:
            self._discard_asset(room_id, round_id, asset_id)
        return result

    def _discard_asset(self, room_id, round_id, asset_id):
        path = f"{root(room_id, round_id)}/assets/{asset_id}"
        doc = self.store.atomic(lambda tx: tx.get(path))
        if doc:
            self.storage.blobs.delete(doc["path"])
            self.store.atomic(lambda tx: tx.delete(path))

    def _visibility(self, tx, base, rd, private, uid):
        require(
            uid not in private["returned_uids"], "HISTORY_LOCKED", 403, "履歴は公開されていません"
        )
        if rd["status"] in ("finished", "failed"):
            return 5
        for index in (1, 2, 3):
            step = tx.get(f"{base}/steps/{index}")
            if step["player_id"] == uid and step["status"] == "done":
                return index
        return -1

    def my_input(self, uid, round_id):
        def work(tx):
            _, base, _, rd, private = self._round(tx, round_id, uid)
            require(
                uid not in private["returned_uids"] and rd["status"] == "playing",
                "NOT_YOUR_TURN",
                403,
            )
            index = rd["current_step_index"]
            step = tx.get(f"{base}/steps/{index}")
            require(step["status"] == "active" and step["player_id"] == uid, "NOT_YOUR_TURN", 403)
            source = private["outputs"].get(str(index - 1), {})
            if index == 2:
                input_data = {"kind": "text", "text": source.get("text", "")}
            else:
                input_data = {
                    "kind": "image" if index == 1 else "video",
                    "asset_id": source.get("asset_id"),
                }
            response = {
                "step_index": index,
                "type": step["type"],
                "deadline_at": step["deadline_at"],
                "input": input_data,
            }
            if step["type"] == "gesture":
                response.update(
                    countdown_seconds=private["config"]["countdown_seconds"],
                    record_seconds=private["config"]["record_seconds"],
                )
            return response

        return self.store.atomic(work)

    def history(self, uid, round_id):
        def work(tx):
            _, base, _, rd, private = self._round(tx, round_id, uid)
            until = self._visibility(tx, base, rd, private, uid)
            steps = []
            for index in range(until + 1):
                step = tx.get(f"{base}/steps/{index}")
                output = private["outputs"].get(str(index), {})
                if output.get("text") is not None:
                    step["text"] = output["text"]
                if output.get("asset_id"):
                    key = "video_asset_id" if index == 2 else "image_asset_id"
                    step[key] = output["asset_id"]
                if index == 2 and private.get("gesture_ai_text") is not None:
                    step["gesture_ai_text"] = private["gesture_ai_text"]
                steps.append(step)
            return {
                "round_status": rd["status"],
                "visible_until_step_index": until,
                "steps": steps,
                "result": tx.get(f"{base}/result/final") if until == 5 else None,
            }

        return self.store.atomic(work)

    def _can_read_asset(self, tx, uid, round_id, asset_id):
        _, base, _, rd, private = self._round(tx, round_id, uid)
        until = self._visibility(tx, base, rd, private, uid)
        doc = tx.get(f"{base}/assets/{asset_id}")
        if doc is None:
            raise ApiError("ASSET_NOT_FOUND", 404, "素材が見つかりません")
        published = private["outputs"].get(str(doc["step_index"]), {})
        if doc["step_index"] <= until and published.get("asset_id") == asset_id:
            return doc
        current = tx.get(f"{base}/steps/{rd['current_step_index']}")
        previous = private["outputs"].get(str(rd["current_step_index"] - 1), {})
        require(
            rd["status"] == "playing"
            and current["status"] == "active"
            and current["player_id"] == uid
            and previous.get("asset_id") == asset_id,
            "HISTORY_LOCKED",
            403,
            "素材は公開されていません",
        )
        return doc

    def can_read_asset(self, uid: str, round_id: str, asset_id: str) -> bool:
        try:
            self.store.atomic(lambda tx: self._can_read_asset(tx, uid, round_id, asset_id))
            return True
        except ApiError:
            return False

    def get_asset(self, uid, round_id, asset_id):
        doc = self.store.atomic(lambda tx: self._can_read_asset(tx, uid, round_id, asset_id))
        return self.storage.blobs.get(doc["path"]), doc["content_type"]

    def _fail(self, tx, room_id, base, room, rd, private, reason):
        rd["status"] = room["status"] = "failed"
        room["fail_reason"] = reason
        rd["revision"] += 1
        tx.set(base, rd)
        tx.set(f"rooms/{room_id}", room)
        for uid in private["players"]:
            if uid not in private["returned_uids"]:
                p = tx.get(f"rooms/{room_id}/players/{uid}")
                p["phase"] = "viewing"
                tx.set(f"rooms/{room_id}/players/{uid}", p)

    def heartbeat(self, uid, room_id):
        # The API maintenance loop and private maintenance endpoint drain the outboxes.
        def work(tx):
            _, player = self._room(tx, room_id, uid)
            player["last_seen_at"] = self.clock()
            tx.set(f"rooms/{room_id}/players/{uid}", player)
            return {"accepted": True}

        return self.store.atomic(work)

    def deadline(self, payload):
        def work(tx):
            room_id, base, room, rd, private = self._round(tx, payload["round_id"])
            require(room_id == payload["room_id"], "INVALID_INPUT", 400)
            if rd["status"] != "playing" or room["current_round_id"] != payload["round_id"]:
                return
            if payload["kind"] == "watchdog":
                check_id = payload.get("check_id")
                if check_id:
                    path = f"{base}/watchdog_checks/{check_id}"
                    if tx.get(path):
                        return
                    tx.set(path, {"checked_at": self.clock()})
                if any(
                    (
                        self.clock() - tx.get(f"rooms/{room_id}/players/{uid}")["last_seen_at"]
                    ).total_seconds()
                    >= self.settings.dropout_after_s
                    for uid in private["players"]
                ):
                    self._fail(tx, room_id, base, room, rd, private, "player_dropped")
                else:
                    self._watchdog(tx, room_id, payload["round_id"])
                return
            index = payload["step_index"]
            step = tx.get(f"{base}/steps/{index}")
            if (
                rd["current_step_index"] != index
                or step["status"] != "active"
                or payload.get("revision") != rd["revision"]
            ):
                return
            due = step["deadline_at"] + timedelta(seconds=self.settings.deadline_grace_s)
            if self.clock() < due:
                return
            if index == 2 and private.get("gesture") and private["gesture"].get("video_asset_id"):
                self._finish_gesture(tx, room_id, payload["round_id"], base, rd, private)
                step = tx.get(f"{base}/steps/2")
                step["timed_out"] = True
                tx.set(f"{base}/steps/2", step)
                self._advance(tx, room_id, payload["round_id"], base, room, rd, private)
            else:
                player = tx.get(f"rooms/{room_id}/players/{step['player_id']}")
                dropped = (
                    self.clock() - player["last_seen_at"]
                ).total_seconds() >= self.settings.dropout_after_s
                step.update(status="timeout", timed_out=True)
                tx.set(f"{base}/steps/{index}", step)
                self._fail(
                    tx,
                    room_id,
                    base,
                    room,
                    rd,
                    private,
                    "player_dropped" if dropped else "communication_failed",
                )

        self.store.atomic(work)
        dispatch_outbox(self.store, self.tasks)

    def _leave_lobby(self, tx, room_id, room, uid):
        """ロビー（待機中）で部屋を出る。本人を外し、ホストなら参加が早い順の次の人に交代する。
        最後の1人が出たら、部屋は空になる（次に入った人がホストになる。join_room を参照）。"""
        tx.delete(f"rooms/{room_id}/players/{uid}")
        if room["host_player_id"] == uid:
            rest = sorted(
                ((key, p) for key, p in tx.list(f"rooms/{room_id}/players") if key != uid),
                key=lambda kp: kp[1]["consented_at"],
            )
            if rest:
                room["host_player_id"] = rest[0][0]
                tx.set(f"rooms/{room_id}", room)
        return {"accepted": True}

    def leave(self, uid, room_id, body):
        def work(tx):
            room, player = self._room(tx, room_id, uid)
            if room["status"] == "waiting":
                return self._leave_lobby(tx, room_id, room, uid)
            round_id = room["current_round_id"]
            require(round_id is not None, "INVALID_STATE")
            base = root(room_id, round_id)
            rd, private = tx.get(base), tx.get(f"{base}/private/main")
            # Explicit return during play is a departure, never a silent skip.
            if rd["status"] == "playing":
                self._fail(tx, room_id, base, room, rd, private, "player_dropped")
            if uid not in private["returned_uids"]:
                private["returned_uids"].append(uid)
            player["phase"] = "returned"
            tx.set(f"rooms/{room_id}/players/{uid}", player)
            tx.set(f"{base}/private/main", private)
            if set(private["returned_uids"]) == set(private["players"]):
                room["status"] = "waiting"
                room["fail_reason"] = None
                tx.set(f"rooms/{room_id}", room)
                for key, p in tx.list(f"rooms/{room_id}/players"):
                    p["phase"] = "lobby"
                    tx.set(f"rooms/{room_id}/players/{key}", p)
                tx.set(
                    f"cleanup_outbox/{room_id}-{round_id}",
                    {"room_id": room_id, "round_id": round_id},
                )
            return {"accepted": True}

        result = self._command(uid, f"leave/{room_id}", body["request_id"], body, work)
        self.cleanup()
        return result

    def cleanup(self):
        try:
            pending = self.store.atomic(lambda tx: tx.list("cleanup_outbox"))
        except Exception:
            logger.exception("Cleanup outbox unavailable; retry later")
            return
        for key, task in pending:
            try:
                self.storage.delete_round_assets(task["room_id"], task["round_id"])
                remaining = self.store.atomic(
                    lambda tx, task=task: tx.list(
                        f"{root(task['room_id'], task['round_id'])}/assets"
                    )
                )
                if not any(doc["kind"] == "video" for _, doc in remaining):
                    self.store.atomic(lambda tx, key=key: tx.delete(f"cleanup_outbox/{key}"))
            except Exception:
                logger.exception("Cleanup remains queued", extra={"round_id": task["round_id"]})
