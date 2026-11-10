from enum import StrEnum


class RoomStatus(StrEnum):
    waiting = "waiting"
    playing = "playing"
    finished = "finished"
    failed = "failed"


class FailReason(StrEnum):
    ai_failed = "ai_failed"
    communication_failed = "communication_failed"
    player_dropped = "player_dropped"


class PlayerPhase(StrEnum):
    lobby = "lobby"
    playing = "playing"
    viewing = "viewing"
    returned = "returned"


class Role(StrEnum):
    A = "A"
    B = "B"
    C = "C"


class StepActor(StrEnum):
    player = "player"
    ai = "ai"


class StepType(StrEnum):
    image_gen = "image_gen"
    text = "text"
    gesture = "gesture"
    conclude = "conclude"


class StepStatus(StrEnum):
    waiting = "waiting"
    active = "active"
    done = "done"
    timeout = "timeout"


class JobStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"


class ResultStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class AssetKind(StrEnum):
    image = "image"
    video = "video"


class JobKind(StrEnum):
    image_gen = "image_gen"
    gesture_read = "gesture_read"
    conclude = "conclude"
    similarity = "similarity"


class ErrorCode(StrEnum):
    ai_failed = "AI_FAILED"
    ai_timeout = "AI_TIMEOUT"
    ai_bad_output = "AI_BAD_OUTPUT"
    ai_blocked = "AI_BLOCKED"
    invalid_input = "INVALID_INPUT"
