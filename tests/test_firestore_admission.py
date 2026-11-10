from threading import Event, Thread
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import Aborted

from backend_a.errors import ApiError
from backend_a.store import FirestoreStore


@pytest.mark.parametrize(
    "error",
    [RuntimeError("callback"), ApiError("INVALID_STATE"), Aborted("contention"), SystemExit(3)],
)
def test_transaction_lock_is_released_for_another_thread_after_error(monkeypatch, error):
    from google.cloud import firestore

    monkeypatch.setattr(firestore, "transactional", lambda fn: fn)
    monkeypatch.setattr("backend_a.store.time.sleep", lambda _: None)
    store = FirestoreStore(MagicMock())

    def fail(tx):
        raise error

    with pytest.raises(type(error)):
        store.atomic(fail)
    outcomes = []

    def next_request():
        outcomes.append(store.atomic(lambda tx: "next request completed"))

    # A same-thread RLock reacquisition could hide a leaked acquisition.
    thread = Thread(target=next_request, daemon=True)
    thread.start()
    thread.join(timeout=3)
    assert not thread.is_alive(), "failed transaction retained the admission lock"
    assert outcomes == ["next request completed"]


def test_admission_is_per_store_and_does_not_lock_an_independent_store(monkeypatch):
    from google.cloud import firestore

    monkeypatch.setattr(firestore, "transactional", lambda fn: fn)
    one, two = FirestoreStore(MagicMock()), FirestoreStore(MagicMock())
    entered, release, completed = Event(), Event(), Event()

    def hold(tx):
        entered.set()
        assert release.wait(5)

    first = Thread(target=lambda: one.atomic(hold), daemon=True)
    second = Thread(target=lambda: (two.atomic(lambda tx: None), completed.set()), daemon=True)
    first.start()
    try:
        assert entered.wait(3)
        second.start()
        assert completed.wait(3), "an independent Store was unnecessarily blocked"
    finally:
        release.set()
        first.join(timeout=3)
        if second.ident is not None:
            second.join(timeout=3)
    assert not first.is_alive() and not second.is_alive()
