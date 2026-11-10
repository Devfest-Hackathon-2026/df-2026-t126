import os

import pytest

from backend_a.errors import ApiError
from backend_a.runtime import build_runtime, localhost_endpoint
from common.settings import Settings


@pytest.mark.skipif(
    os.environ.get("RUN_FIRESTORE_EMULATOR_TESTS") != "1", reason="Requires local Auth emulator"
)
def test_anonymous_auth_emulator_token_and_wrong_project():
    import httpx

    host = os.environ.get("FIREBASE_AUTH_EMULATOR_HOST", "")
    localhost_endpoint(host)
    response = httpx.post(
        f"http://{host}/identitytoolkit.googleapis.com/v1/accounts:signUp?key=fake-key",
        json={"returnSecureToken": True},
        trust_env=False,
    )
    response.raise_for_status()
    runtime = build_runtime(Settings(runtime_mode="emulator"))
    token = response.json()["idToken"]
    uid = runtime.auth.verify(token)
    assert uid == response.json()["localId"]
    with pytest.raises(ApiError):
        runtime.auth.verify("not-a-jwt")
    other_project = build_runtime(Settings(runtime_mode="emulator", project_id="demo-other"))
    with pytest.raises(ApiError):
        other_project.auth.verify(token)
