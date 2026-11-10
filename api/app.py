import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from threading import Lock
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, Header, Path, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from api.models import CreateRoom, Deadline, GestureFinish, JoinRoom, Request, SelectRole, Submit
from backend_a.errors import ApiError
from backend_a.maintenance import maintenance_once
from backend_a.maintenance_process import run_cloud_maintenance
from backend_a.progress import configure_progress
from backend_a.runtime import build_runtime
from common.models import GestureBatch
from common.storage import configure_storage

logger = logging.getLogger(__name__)
SafeID = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,128}$")]


class BodyLimit:
    """Count streaming bodies before multipart/JSON parsing, not just Content-Length."""

    def __init__(self, app, json_limit, video_limit):
        self.app, self.json_limit, self.video_limit = app, json_limit, video_limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        video = scope["path"].endswith("/gesture/video")
        limit = self.video_limit + 65536 if video else self.json_limit
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > limit:
                response = JSONResponse(
                    {"error": {"code": "PAYLOAD_TOO_LARGE", "message": "送信データが大きすぎます"}},
                    status_code=400,
                    headers={"Cache-Control": "no-store, private"},
                )
                return await response(scope, receive, send)
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, bounded, send)


def create_app(runtime=None, *, internal=False, maintenance_endpoint=False):
    if maintenance_endpoint and not internal:
        raise ValueError("Maintenance endpoint requires the private internal application")
    runtime = runtime or build_runtime()
    game, settings = runtime.game, runtime.settings

    async def maintenance():
        while True:
            await asyncio.sleep(5)
            try:
                await run_in_threadpool(maintenance_once, game)
            except Exception:
                logger.exception("Maintenance will retry")

    @asynccontextmanager
    async def lifespan(app):
        configure_progress(game)
        configure_storage(game.storage)
        # Scheduler-driven private service never starts an independent loop.
        # A request invokes exactly one pass; API/Worker retain their old loop.
        task = None if maintenance_endpoint else asyncio.create_task(maintenance())
        app.state.maintenance_task = task
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(
        title="Gesture Relay Backend A",
        lifespan=lifespan,
        docs_url="/docs" if settings.runtime_mode == "local" else None,
        redoc_url=None,
    )
    app.state.runtime = runtime
    default_openapi = app.openapi

    def specification_openapi():
        schema = default_openapi()
        error_schema = {
            "type": "object",
            "required": ["error"],
            "properties": {
                "error": {
                    "type": "object",
                    "required": ["code", "message"],
                    "properties": {"code": {"type": "string"}, "message": {"type": "string"}},
                }
            },
        }
        for item in schema["paths"].values():
            for operation in item.values():
                if not isinstance(operation, dict) or "responses" not in operation:
                    continue
                # FastAPI documents 422 automatically, while S1 requires our 400 envelope.
                responses = operation["responses"]
                if responses.pop("422", None) is not None:
                    responses["400"] = {
                        "description": "入力内容を確認してください",
                        "content": {"application/json": {"schema": error_schema}},
                    }
        return schema

    app.openapi = specification_openapi

    @app.middleware("http")
    async def private_responses(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    app.add_middleware(
        BodyLimit, json_limit=settings.json_max_bytes, video_limit=settings.video_max_bytes
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.exception_handler(ApiError)
    async def api_error(request, exc):
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            {"error": {"code": "INVALID_INPUT", "message": "入力内容を確認してください"}},
            status_code=400,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        code = "ROOM_NOT_FOUND" if exc.status_code == 404 else "INVALID_INPUT"
        return JSONResponse(
            {"error": {"code": code, "message": "操作を受け付けられません"}},
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        logger.error("Unhandled API failure", exc_info=exc)
        return JSONResponse(
            {"error": {"code": "INTERNAL", "message": "処理に失敗しました"}}, status_code=500
        )

    def token(authorization):
        if not authorization or not authorization.startswith("Bearer "):
            raise ApiError("UNAUTHENTICATED", 401, "ログインが必要です")
        return authorization[7:]

    def uid(authorization: Annotated[str | None, Header()] = None):
        return runtime.auth.verify(token(authorization))

    User = Annotated[str, Depends(uid)]

    @app.get("/healthz")
    def health():
        return {"status": "ok", "mode": settings.runtime_mode}

    @app.get("/health")
    def worker_compatible_health():
        return {"ok": True}

    # A separate internal-only ASGI application is deployed under Run IAM.
    # /internal routes are absent entirely from the public API application.
    if internal:

        def verify_internal(authorization: Annotated[str | None, Header()] = None):
            runtime.internal_auth.verify(token(authorization))

        if maintenance_endpoint:
            maintenance_lock = Lock()

            @app.post("/internal/maintenance", dependencies=[Depends(verify_internal)])
            def maintain():
                if settings.runtime_mode == "cloud":
                    # One child per instance. Duplicate requests on another
                    # instance remain safe through the persisted checkpoints.
                    if not maintenance_lock.acquire(blocking=False):
                        raise ApiError("INTERNAL", 500, "保守処理を再試行してください")
                    try:
                        run_cloud_maintenance(settings)
                    finally:
                        maintenance_lock.release()
                else:
                    # Local/emulator MemoryTasks must stay in the parent so
                    # mock deliveries are not lost when a child exits.
                    maintenance_once(game)
                return {"accepted": True}

        @app.post("/internal/deadlines", dependencies=[Depends(verify_internal)])
        def deadline(body: Deadline):
            if body.kind == "step" and (body.step_index is None or body.revision is None):
                raise ApiError("INVALID_INPUT", 400, "期限情報が不足しています")
            game.deadline(body.model_dump())
            return {"accepted": True}

        return app

    @app.post("/api/rooms")
    def create_room(body: CreateRoom, user: User):
        return game.create_room(user, body.model_dump(mode="json"))

    @app.post("/api/rooms/join")
    def join_room(body: JoinRoom, user: User):
        return game.join_room(user, body.model_dump(mode="json"))

    @app.post("/api/rooms/{room_id}/role")
    def role(room_id: SafeID, body: SelectRole, user: User):
        return game.select_role(user, room_id, body.model_dump(mode="json"))

    @app.post("/api/rooms/{room_id}/start", status_code=202)
    def start(room_id: SafeID, body: Request, user: User):
        return game.start(user, room_id, body.model_dump(mode="json"))

    @app.get("/api/rounds/{round_id}/my-input")
    def my_input(round_id: SafeID, user: User):
        return game.my_input(user, round_id)

    @app.post("/api/rounds/{round_id}/steps/{step_index}/submit", status_code=202)
    def submit(
        round_id: SafeID, step_index: Annotated[int, Path(ge=0, le=5)], body: Submit, user: User
    ):
        return game.submit(user, round_id, step_index, body.model_dump(mode="json"))

    @app.post("/api/rounds/{round_id}/gesture/start")
    def gesture_start(round_id: SafeID, body: Request, user: User):
        return game.gesture_start(user, round_id, body.model_dump(mode="json"))

    @app.post("/api/rounds/{round_id}/gesture/batches", status_code=202)
    def batches(round_id: SafeID, body: GestureBatch, user: User):
        return game.batches(user, round_id, body.model_dump(mode="json"))

    @app.post("/api/rounds/{round_id}/gesture/finish", status_code=202)
    def finish(round_id: SafeID, body: GestureFinish, user: User):
        return game.gesture_finish(user, round_id, body.model_dump(mode="json"))

    @app.post("/api/rounds/{round_id}/gesture/video")
    async def video(
        round_id: SafeID,
        user: User,
        gesture_session_id: Annotated[str, Form(pattern=r"^[A-Za-z0-9_-]{1,128}$")],
        request_id: Annotated[UUID, Form()],
        file: Annotated[UploadFile, File()],
    ):
        try:
            data = await file.read(settings.video_max_bytes + 1)
            if len(data) > settings.video_max_bytes:
                raise ApiError("PAYLOAD_TOO_LARGE", 400, "録画のサイズが大きすぎます")
            body = GestureFinish(request_id=request_id, gesture_session_id=gesture_session_id)
            return await run_in_threadpool(
                game.upload_video,
                user,
                round_id,
                body.model_dump(mode="json"),
                data,
                file.content_type,
            )
        finally:
            await file.close()

    @app.get("/api/rounds/{round_id}/history")
    def history(round_id: SafeID, user: User):
        return game.history(user, round_id)

    @app.get("/api/rounds/{round_id}/assets/{asset_id}")
    def asset(round_id: SafeID, asset_id: SafeID, user: User):
        data, content_type = game.get_asset(user, round_id, asset_id)
        return Response(
            data,
            media_type=content_type,
            headers={"Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff"},
        )

    @app.post("/api/rooms/{room_id}/leave")
    def leave(room_id: SafeID, body: Request, user: User):
        return game.leave(user, room_id, body.model_dump(mode="json"))

    @app.post("/api/rooms/{room_id}/heartbeat")
    def heartbeat(room_id: SafeID, user: User):
        return game.heartbeat(user, room_id)

    return app
