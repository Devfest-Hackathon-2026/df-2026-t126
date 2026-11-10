"""Verifiers are injected; the local verifier never contacts Firebase."""

import re

from backend_a.errors import ApiError


class LocalAuth:
    def verify(self, token: str) -> str:
        # Deliberately explicit fake token; only wired in the local runtime.
        if not re.fullmatch(r"local:[A-Za-z0-9_-]{1,128}", token):
            raise ApiError("UNAUTHENTICATED", 401, "ログインし直してください")
        return token[6:]


class FirebaseAuth:
    def __init__(self, app):
        self.app = app

    def verify(self, token):
        from firebase_admin import auth

        try:
            claims = auth.verify_id_token(token, app=self.app, check_revoked=True)
            uid = claims["uid"]
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", uid):
                raise ValueError("Unsafe uid")
            return uid
        except (
            ValueError,
            auth.InvalidIdTokenError,
            auth.UserDisabledError,
            auth.UserNotFoundError,
            KeyError,
            auth.CertificateFetchError,
        ) as exc:
            raise ApiError("UNAUTHENTICATED", 401, "ログインし直してください") from exc


class DenyInternalAuth:
    def verify(self, token):
        # Tests call service callbacks directly. No public local worker bypass.
        raise ApiError("UNAUTHENTICATED", 401, "内部認証が必要です")


class GoogleInternalAuth:
    def __init__(self, audience, service_account):
        if not audience or not service_account:
            raise ValueError("Internal audience and allowed service account are required")
        self.audience, self.service_account = audience, service_account

    def verify(self, token):
        from google.auth.transport.requests import Request
        from google.oauth2.id_token import verify_oauth2_token

        try:
            claims = verify_oauth2_token(token, Request(), audience=self.audience)
            if (
                claims.get("email") != self.service_account
                or claims.get("email_verified") is not True
            ):
                raise ValueError("Wrong service identity")
        except (ValueError, KeyError) as exc:
            raise ApiError("UNAUTHENTICATED", 401, "内部認証が必要です") from exc
