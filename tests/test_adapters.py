import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import AlreadyExists

from api.app import create_app
from backend_a.auth import FirebaseAuth, GoogleInternalAuth
from backend_a.errors import ApiError
from backend_a.runtime import build_runtime
from backend_a.store import FirestoreStore
from backend_a.tasks import CloudTasks, MemoryTasks, dispatch_outbox
from common.settings import Settings


def test_firestore_flushes_only_after_reads_and_supports_read_own_writes(monkeypatch):
    from google.cloud import firestore

    events = []
    client, raw = MagicMock(), MagicMock()
    client.transaction.return_value = raw
    document = client.document.return_value
    document.get.side_effect = lambda **kwargs: (
        events.append("read") or SimpleNamespace(to_dict=lambda: {"n": 1})
    )
    raw.set.side_effect = lambda *args: events.append("write")
    monkeypatch.setattr(firestore, "transactional", lambda f: f)

    def callback(tx):
        assert tx.get("c/key") == {"n": 1}
        snapshot = tx.get("c/key")
        snapshot["n"] = 100
        assert tx.get("c/key") == {"n": 1}
        tx.set("c/key", {"n": 2})
        assert tx.get("c/key") == {"n": 2}
        assert tx.get("c/other") == {"n": 1}
        assert "write" not in events

    FirestoreStore(client).atomic(callback)
    assert events == ["read", "read", "write"]


@pytest.mark.parametrize("wrapped", [False, True])
def test_firestore_retries_aborted_with_fresh_transaction_only(monkeypatch, wrapped):
    from google.api_core.exceptions import Aborted
    from google.cloud import firestore

    client = MagicMock()
    client.transaction.side_effect = [MagicMock(), MagicMock()]
    seen = []

    def decorate(callback):
        def run(transaction):
            seen.append(transaction)
            if len(seen) == 1:
                if wrapped:
                    raise ValueError("SDK commit retry budget exhausted") from Aborted("contention")
                raise Aborted("read contention")
            return "committed"

        return run

    monkeypatch.setattr(firestore, "transactional", decorate)
    monkeypatch.setattr("backend_a.store.time.sleep", lambda _: None)
    assert FirestoreStore(client).atomic(lambda tx: None) == "committed"
    assert seen[0] is not seen[1]
    assert all(call.kwargs == {"max_attempts": 1} for call in client.transaction.call_args_list)


def test_firestore_contention_retry_budget_is_bounded(monkeypatch):
    from google.api_core.exceptions import Aborted
    from google.cloud import firestore

    client = MagicMock()

    def decorate(callback):
        def run(transaction):
            raise Aborted("contention")

        return run

    monkeypatch.setattr(firestore, "transactional", decorate)
    sleep = MagicMock()
    monkeypatch.setattr("backend_a.store.time.sleep", sleep)
    with pytest.raises(Aborted):
        FirestoreStore(client).atomic(lambda tx: None)
    assert client.transaction.call_count == 8 and sleep.call_count == 7
    assert all(0.02 <= call.args[0] <= 2 for call in sleep.call_args_list)


def test_firestore_does_not_retry_noncontention_errors(monkeypatch):
    from google.cloud import firestore

    client = MagicMock()

    def decorate(callback):
        def run(transaction):
            raise ValueError("bad application data")

        return run

    monkeypatch.setattr(firestore, "transactional", decorate)
    with pytest.raises(ValueError, match="bad application data"):
        FirestoreStore(client).atomic(lambda tx: None)
    client.transaction.assert_called_once()


def test_firebase_sdk_verifies_token_revocation_and_rejects_bad_uid(monkeypatch):
    from firebase_admin import auth

    verify = MagicMock(return_value={"uid": "anonymous-user"})
    monkeypatch.setattr(auth, "verify_id_token", verify)
    app = object()
    assert FirebaseAuth(app).verify("signed") == "anonymous-user"
    verify.assert_called_once_with("signed", app=app, check_revoked=True)
    for error in (
        ValueError("bad"),
        auth.RevokedIdTokenError("revoked"),
        auth.UserDisabledError("disabled"),
    ):
        verify.side_effect = error
        with pytest.raises(ApiError) as exc:
            FirebaseAuth(app).verify("bad")
        assert exc.value.status == 401
    verify.side_effect = None
    verify.return_value = {"uid": "../escape"}
    with pytest.raises(ApiError):
        FirebaseAuth(app).verify("bad")


def test_internal_oidc_checks_audience_and_exact_service_identity(monkeypatch):
    from google.oauth2 import id_token

    verify = MagicMock(
        return_value={"email": "tasks@example.iam.gserviceaccount.com", "email_verified": True}
    )
    monkeypatch.setattr(id_token, "verify_oauth2_token", verify)
    verifier = GoogleInternalAuth(
        "https://deadline.example", "tasks@example.iam.gserviceaccount.com"
    )
    verifier.verify("signed")
    assert verify.call_args.kwargs["audience"] == "https://deadline.example"
    verify.return_value = {"email": "attacker@example.com", "email_verified": True}
    with pytest.raises(ApiError):
        verifier.verify("signed-by-google-but-wrong-user")


def test_cloud_tasks_only_serializes_references_and_uses_oidc(h):
    settings = Settings(
        project_id="demo-gesture-relay",
        tasks_location="local",
        tasks_queue="queue",
        tasks_service_account="tasks@example.com",
        worker_url="https://worker.example/internal/jobs",
        deadline_url="https://deadline.example/internal/deadlines",
    )
    client = MagicMock()
    client.queue_path.return_value = "projects/demo/locations/local/queues/queue"
    adapter = CloudTasks(client, settings)
    payload = {"job_id": "j", "kind": "image_gen", "room_id": "r", "round_id": "g", "revision": 1}
    adapter.send("task-key", {"target": "worker", "payload": payload})
    task = client.create_task.call_args.kwargs["request"]["task"]
    assert task["http_request"]["url"] == settings.worker_url
    assert task["http_request"]["oidc_token"]["audience"] == "https://worker.example"
    assert json.loads(task["http_request"]["body"]) == payload
    client.create_task.side_effect = AlreadyExists("replayed")
    adapter.send("task-key", {"target": "worker", "payload": payload})
    settings.worker_url = "http://insecure.example/internal/jobs"
    with pytest.raises(ValueError):
        adapter.send("task-key", {"target": "worker", "payload": payload})


def test_outbox_recovers_delivery_failure_and_skips_sent_pages(h):
    h.start()
    h.store.atomic(lambda tx: tx.set("task_outbox/recovery", {"sent": False, "payload": {}}))
    sender = MagicMock()
    sender.send.side_effect = RuntimeError("queue temporarily unavailable")
    dispatch_outbox(h.store, sender)
    assert not h.store.atomic(lambda tx: tx.get("task_outbox/recovery"))["sent"]
    sender = MemoryTasks()
    dispatch_outbox(h.store, sender)
    assert "recovery" in sender.messages
    h.store.atomic(lambda tx: tx.set("task_outbox/new", {"sent": False, "payload": {}}))
    dispatch_outbox(h.store, sender, limit=1)
    assert "new" in sender.messages


def test_runtime_local_never_discovers_credentials_and_emulator_refuses_fallback(monkeypatch):
    import google.auth

    default = MagicMock(side_effect=AssertionError("ADC must never be read"))
    monkeypatch.setattr(google.auth, "default", default)
    build_runtime(Settings())
    default.assert_not_called()
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    with pytest.raises(ValueError):
        build_runtime(Settings(runtime_mode="emulator"))
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "production.example:8080")
    with pytest.raises(ValueError):
        build_runtime(Settings(runtime_mode="emulator"))
    default.assert_not_called()


def test_google_storage_lifecycle_missing_blob_is_asset_not_found():
    from google.api_core.exceptions import NotFound

    from common.storage import GoogleBlobs

    bucket = MagicMock()
    bucket.blob.return_value.download_as_bytes.side_effect = NotFound("expired by lifecycle")
    with pytest.raises(ApiError) as error:
        GoogleBlobs(bucket).get("rooms/r/rounds/g/images/expired.png")
    assert error.value.status == 404 and error.value.code == "ASSET_NOT_FOUND"


def test_internal_app_rejects_client_token_and_is_not_public(h):
    from fastapi.testclient import TestClient

    client = TestClient(create_app(h.runtime, internal=True))
    response = client.post(
        "/internal/deadlines",
        headers={"Authorization": "Bearer local:a"},
        json={"room_id": "r", "round_id": "g", "kind": "watchdog"},
    )
    assert response.status_code == 401
    assert client.post("/api/rooms", json={}).status_code == 404
    client.close()


def test_join_retry_is_not_rate_limited_and_reuse_changed_body_rejected(h):
    h.lobby()
    body = {
        "request_id": "9a23712e-1df6-4355-b764-32fe276450f5",
        "name": "b",
        "consented": True,
        "join_code": h.code,
    }
    first = h.post("/api/rooms/join", "b", body)
    for _ in range(20):
        assert h.post("/api/rooms/join", "b", body) == first
    h.post("/api/rooms/join", "b", {**body, "name": "changed"}, 400)


def test_missing_text_does_not_become_empty_submission_and_stale_deadline_ignored(h):
    h.start()
    h.complete("image_gen", 0)
    h.clock.advance(66)
    h.game.deadline(
        {
            "room_id": h.room_id,
            "round_id": h.round_id,
            "kind": "step",
            "step_index": 1,
            "revision": -1,
        }
    )
    assert h.doc()["status"] == "playing"
    response = h.post(
        f"/api/rounds/{h.round_id}/steps/1/submit", body={"text": "late"}, expected=409
    )
    assert response["error"]["code"] == "DEADLINE_PASSED"
    assert "1" not in h.doc("/private/main")["outputs"]


def test_streamed_body_limit_and_private_response_headers(h):
    h.settings.json_max_bytes = 1024
    # Middleware captures settings at app construction.
    from fastapi.testclient import TestClient

    client = TestClient(create_app(h.runtime), raise_server_exceptions=False)
    response = client.post(
        "/api/rooms",
        headers={"Authorization": "Bearer local:a", "Content-Type": "application/json"},
        content=iter([b'{"name":"' + b"x" * 2000, b'"}']),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert client.get("/healthz").headers["Cache-Control"] == "no-store, private"
    client.close()


def test_outbox_purges_old_sent_records_but_keeps_recent_and_unsent(h):
    """送信済みの記録が溜まると、保守のたびに全件を読んで重くなる。古い送信済みだけ消す。"""
    from datetime import UTC, datetime, timedelta

    from backend_a.tasks import SENT_RETENTION_S, purge_sent_outbox

    now = datetime.now(UTC)
    old = now - timedelta(seconds=SENT_RETENTION_S + 60)

    def seed(tx):
        tx.set("task_outbox/legacy", {"sent": True, "payload": {}})  # sent_at なし（古い形式）
        tx.set("task_outbox/old", {"sent": True, "sent_at": old, "payload": {}})
        tx.set("task_outbox/recent", {"sent": True, "sent_at": now, "payload": {}})
        tx.set("task_outbox/unsent", {"sent": False, "payload": {}})

    h.store.atomic(seed)
    purge_sent_outbox(h.store)
    sender = MemoryTasks()
    dispatch_outbox(h.store, sender)
    left = {key for key, _ in h.store.atomic(lambda tx: tx.list("task_outbox"))}
    assert "legacy" not in left and "old" not in left
    assert "recent" in left
    assert "unsent" in left  # 未送信は消さない（送信されて、送信済みになる）
    assert "unsent" in sender.messages
    assert h.store.atomic(lambda tx: tx.get("task_outbox/unsent"))["sent_at"] is not None
