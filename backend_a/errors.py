from enum import StrEnum


class ApiErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    TEXT_TOO_LONG = "TEXT_TOO_LONG"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    NOT_YOUR_TURN = "NOT_YOUR_TURN"
    NOT_HOST = "NOT_HOST"
    CONSENT_REQUIRED = "CONSENT_REQUIRED"
    HISTORY_LOCKED = "HISTORY_LOCKED"
    ROOM_NOT_FOUND = "ROOM_NOT_FOUND"
    ASSET_NOT_FOUND = "ASSET_NOT_FOUND"
    ALREADY_SUBMITTED = "ALREADY_SUBMITTED"
    DEADLINE_PASSED = "DEADLINE_PASSED"
    ROLE_TAKEN = "ROLE_TAKEN"
    ROOM_FULL = "ROOM_FULL"
    ROLES_NOT_READY = "ROLES_NOT_READY"
    INVALID_STATE = "INVALID_STATE"
    TOO_MANY_ATTEMPTS = "TOO_MANY_ATTEMPTS"
    INTERNAL = "INTERNAL"


class ApiError(Exception):
    def __init__(self, code: str, status: int = 409, message: str = "操作を受け付けられません"):
        self.code, self.status, self.message = str(code), status, message
        super().__init__(self.code)


def require(condition, code, status=409, message="操作を受け付けられません"):
    if not condition:
        raise ApiError(code, status, message)
