"""Small document store; callbacks are pure w.r.t. external side effects.

Firestore writes are buffered until every read is complete. A callback can be
retried by Firestore: never send tasks or write blobs from inside it.
"""

from __future__ import annotations

import random
import time
from copy import deepcopy
from itertools import islice
from threading import RLock
from typing import Protocol


class Transaction(Protocol):
    def get(self, path: str) -> dict | None: ...
    def list(self, collection: str) -> list[tuple[str, dict]]: ...
    def set(self, path: str, value: dict) -> None: ...
    def delete(self, path: str) -> None: ...
    def select(
        self, collection: str, limit: int, *, where=None, after: str | None = None
    ) -> list[tuple[str, dict]]:
        """Read a bounded page before writing. An ID cursor is for unfiltered scans."""
        ...


class MemoryTransaction:
    def __init__(self, docs):
        self.docs = docs

    def get(self, path):
        return deepcopy(self.docs.get(path))

    def list(self, collection):
        prefix = collection + "/"
        return [
            (p.rsplit("/", 1)[1], deepcopy(v))
            for p, v in self.docs.items()
            if p.startswith(prefix) and "/" not in p[len(prefix) :]
        ]

    def set(self, path, value):
        self.docs[path] = deepcopy(value)

    def delete(self, path):
        self.docs.pop(path, None)

    def select(self, collection, limit, *, where=None, after=None):
        prefix = collection + "/"
        ids = sorted(
            path[len(prefix) :]
            for path in self.docs
            if path.startswith(prefix) and "/" not in path[len(prefix) :]
        )
        docs = ((key, self.docs[prefix + key]) for key in ids if after is None or key > after)
        if where is not None:
            field, op, value = where
            if op == "==":
                docs = ((key, doc) for key, doc in docs if field in doc and doc[field] == value)
            elif op == "<":
                docs = (
                    (key, doc)
                    for key, doc in docs
                    if doc.get(field) is not None and doc[field] < value
                )
            else:
                raise ValueError(f"Unsupported query operator: {op}")
        return [(key, deepcopy(doc)) for key, doc in islice(docs, limit)]


class MemoryStore:
    def __init__(self):
        self.docs = {}
        self.lock = RLock()

    def atomic(self, callback):
        with self.lock:
            working = deepcopy(self.docs)
            result = callback(MemoryTransaction(working))
            self.docs = working
            return result


class FirestoreTransaction:
    def __init__(self, client, transaction):
        self.client, self.transaction = client, transaction
        self.pending = {}
        self.reads = {}
        self.queries = {}

    def get(self, path):
        if path in self.pending:
            return deepcopy(self.pending[path])
        if path not in self.reads:
            self.reads[path] = (
                self.client.document(path).get(transaction=self.transaction).to_dict()
            )
        return deepcopy(self.reads[path])

    def list(self, collection):
        if collection not in self.queries:
            self.queries[collection] = {
                doc.id: doc.to_dict()
                for doc in self.client.collection(collection).stream(transaction=self.transaction)
            }
            for key, value in self.queries[collection].items():
                self.reads.setdefault(f"{collection}/{key}", value)
        values = deepcopy(self.queries[collection])
        prefix = collection + "/"
        for path, data in self.pending.items():
            if path.startswith(prefix) and "/" not in path[len(prefix) :]:
                key = path[len(prefix) :]
                if data is None:
                    values.pop(key, None)
                else:
                    values[key] = deepcopy(data)
        return list(values.items())

    def set(self, path, value):
        self.pending[path] = deepcopy(value)

    def delete(self, path):
        self.pending[path] = None

    def flush(self):
        for path, data in self.pending.items():
            ref = self.client.document(path)
            if data is None:
                self.transaction.delete(ref)
            else:
                self.transaction.set(ref, data)

    def select(self, collection, limit, *, where=None, after=None):
        from google.cloud.firestore_v1.base_query import FieldFilter

        if self.pending:
            raise ValueError("Bounded queries must precede transaction writes")
        query = self.client.collection(collection)
        if where is not None:
            query = query.where(filter=FieldFilter(*where))
        if after is not None:
            cursor = self.client.document(f"{collection}/{after}")
            query = query.order_by("__name__").start_after({"__name__": cursor})
        return [
            (doc.id, doc.to_dict())
            for doc in query.limit(limit).stream(transaction=self.transaction)
        ]


class FirestoreStore:
    def __init__(self, client):
        self.client = client
        # Multiple local readers upgrading the same Firestore locks can exhaust
        # every retry together. Admit one pure transaction callback per store,
        # as MemoryStore does. Firestore still arbitrates across processes.
        self._transaction_lock = RLock()

    def atomic(self, callback):
        with self._transaction_lock:
            return self._atomic(callback)

    def _atomic(self, callback):
        from google.api_core.exceptions import Aborted
        from google.cloud import firestore

        @firestore.transactional
        def run(transaction):
            unit = FirestoreTransaction(self.client, transaction)
            result = callback(unit)
            unit.flush()
            return result

        # Immediate SDK retries can repeatedly collide when multiple readers
        # try to upgrade the same document lock (reproduced in the emulator).
        # Own the single bounded retry budget, starting a fresh snapshot with
        # exponential full jitter after each confirmed ABORTED failure.
        # Never retry business errors or arbitrary ValueErrors.
        for attempt in range(8):
            try:
                return run(self.client.transaction(max_attempts=1))
            except (Aborted, ValueError) as exc:
                aborted = isinstance(exc, Aborted) or isinstance(exc.__cause__, Aborted)
                if not aborted or attempt == 7:
                    raise
                time.sleep(random.uniform(0.02, min(2.0, 0.1 * 2**attempt)))
