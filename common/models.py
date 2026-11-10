from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from common.enums import AssetKind, ErrorCode, JobKind, JobStatus


class JobPayload(BaseModel):
    job_id: str
    kind: JobKind
    room_id: str
    round_id: str
    step_index: int | None = None
    revision: int


class ErrorInfo(BaseModel):
    code: ErrorCode
    message: str
    retryable: bool


class JobResult(BaseModel):
    ok: bool
    text: str | None = None
    asset_id: str | None = None
    score: float | None = None
    error: ErrorInfo | None = None


class JobDoc(BaseModel):
    kind: JobKind
    status: JobStatus
    attempt: int = 0
    max_attempts: int = 3
    last_error: ErrorInfo | None = None
    revision: int


class JobPolicy(BaseModel):
    max_attempts: int = 3
    fatal: bool


JOB_POLICY = {kind: JobPolicy(fatal=kind != JobKind.gesture_read) for kind in JobKind}


class AssetDoc(BaseModel):
    kind: AssetKind
    path: str
    content_type: str
    size_bytes: int
    step_index: int
    created_at: datetime


VIDEO_EXTENSIONS = {"video/webm": "webm", "video/mp4": "mp4"}


class Landmark(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    x: float
    y: float
    z: float


class Hand(BaseModel):
    handedness: Literal["Left", "Right"]
    landmarks: list[Landmark] = Field(min_length=21, max_length=21)


class Sample(BaseModel):
    timestamp_ms: int = Field(ge=0, le=2**63 - 1)
    hands: list[Hand] = Field(max_length=2)


class GestureBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gesture_session_id: str = Field(min_length=1, max_length=128, pattern=r"^[\w-]+$")
    sequence_number: int = Field(ge=0, le=2**31 - 1)
    mirrored: bool
    samples: list[Sample] = Field(max_length=1000)


class GameConfig(BaseModel):
    text_seconds: int = Field(default=60, ge=1, le=600)
    countdown_seconds: int = Field(default=15, ge=0, le=30)
    record_seconds: int = Field(default=8, ge=1, le=30)
