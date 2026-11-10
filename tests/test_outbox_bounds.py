from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from google.api_core.exceptions import AlreadyExists

from backend_a.tasks import (
    LEGACY_SCAN,
    OUTBOX,
    SENT_RETENTION_S,
    CloudTasks,
    MemoryTasks,
    dispatch_outbox,
    purge_sent_outbox,
)


def test_outbox_drains_bounded_pages_without_listing_the_collection(h, monkeypatch):
    now = datetime.now(UTC)
    old = now - timedelta(seconds=SENT_RETENTION_S + 1)

    def seed(tx):
        for index in range(12):
            tx.set(f"{OUTBOX}/pending-{index:02}", {"sent": False})
            tx.set(f"{OUTBOX}/expired-{index:02}", {"sent": True, "sent_at": old})
            tx.set(f"{OUTBOX}/retained-{index:02}", {"sent": True, "sent_at": now})

    h.store.atomic(seed)
    transaction_type = h.store.atomic(type)
    select = transaction_type.select
    queries = []

    def record(tx, collection, limit, **kwargs):
        docs = select(tx, collection, limit, **kwargs)
        queries.append((collection, limit, len(docs)))
        return docs

    def forbid_list(*args):
        raise AssertionError("Outbox must not use an unbounded list")

    monkeypatch.setattr(transaction_type, "select", record)
    monkeypatch.setattr(transaction_type, "list", forbid_list)
    sender = MemoryTasks()
    for page in range(3):
        purge_sent_outbox(h.store, limit=4)
        dispatch_outbox(h.store, sender, limit=4)
        assert len(sender.messages) == 4 * (page + 1)

    assert queries == [(OUTBOX, 4, 4)] * 6
    assert h.store.atomic(lambda tx: tx.get(f"{OUTBOX}/expired-11")) is None
    assert h.store.atomic(lambda tx: tx.get(f"{OUTBOX}/retained-11")) is not None


def test_legacy_scan_resumes_after_deleted_cursor_and_recovers_pending(h):
    def seed(tx):
        tx.set(f"{OUTBOX}/a", {"sent": True})
        tx.set(f"{OUTBOX}/b", {})
        tx.set(f"{OUTBOX}/c", {"sent": True})

    h.store.atomic(seed)
    sender = MemoryTasks()
    for _ in range(4):
        purge_sent_outbox(h.store, limit=1)
        dispatch_outbox(h.store, sender, limit=1)
    assert list(sender.messages) == ["b"]
    assert h.store.atomic(lambda tx: tx.list(OUTBOX))[0][0] == "b"
    assert h.store.atomic(lambda tx: tx.get(LEGACY_SCAN))["next_scan_at"] > datetime.now(UTC)

    # A rollback or an older worker may still write legacy records.
    def seed_after_scan(tx):
        tx.set(f"{OUTBOX}/late", {"sent": True})
        tx.set(LEGACY_SCAN, {"next_scan_at": datetime.now(UTC) - timedelta(seconds=1)})

    h.store.atomic(seed_after_scan)
    purge_sent_outbox(h.store, limit=4)
    assert h.store.atomic(lambda tx: tx.get(f"{OUTBOX}/late")) is None


def test_failed_ack_retries_same_task_name_and_accepts_already_exists(h, monkeypatch):
    h.settings.worker_url = "https://worker.example/tasks/run"
    h.settings.tasks_service_account = "test@example.com"
    client = Mock()
    client.queue_path.return_value = "projects/demo/locations/local/queues/test"
    client.create_task.side_effect = [None, AlreadyExists("already sent")]
    sender = CloudTasks(client, h.settings)
    path = f"{OUTBOX}/retry"
    h.store.atomic(lambda tx: tx.set(path, {"sent": False, "target": "worker", "payload": {}}))
    atomic = h.store.atomic

    def fail_first_ack(callback):
        if client.create_task.call_count == 1:
            raise RuntimeError("ack unavailable")
        return atomic(callback)

    with monkeypatch.context() as patch:
        patch.setattr(h.store, "atomic", fail_first_ack)
        dispatch_outbox(h.store, sender, limit=1)
    assert not h.store.atomic(lambda tx: tx.get(path))["sent"]
    dispatch_outbox(h.store, sender, limit=1)
    assert h.store.atomic(lambda tx: tx.get(path))["sent"]
    calls = client.create_task.call_args_list
    assert len(calls) == 2
    assert calls[0].kwargs["request"]["task"]["name"] == calls[1].kwargs["request"]["task"]["name"]
