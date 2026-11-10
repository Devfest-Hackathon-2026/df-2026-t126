from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID


class CreateRoom(Request):
    name: str = Field(min_length=1, max_length=40)
    consented: bool

    @field_validator("name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Name must not be blank")
        return value


class JoinRoom(CreateRoom):
    join_code: str = Field(pattern=r"^\d{4}$")


class SelectRole(Request):
    role: Literal["A", "B", "C"] | None


class Submit(Request):
    text: str
    is_auto: bool = False


class GestureFinish(Request):
    gesture_session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")


class Deadline(BaseModel):
    model_config = ConfigDict(extra="forbid")
    room_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    round_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    kind: Literal["step", "watchdog"]
    step_index: int | None = Field(default=None, ge=0, le=5)
    revision: int | None = Field(default=None, ge=0)
    check_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,128}$")

    @field_validator("step_index")
    @classmethod
    def player_step(cls, value):
        if value not in (None, 1, 2, 3):
            raise ValueError("Only player steps have deadlines")
        return value
