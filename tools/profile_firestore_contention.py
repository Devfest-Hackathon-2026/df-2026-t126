"""Local Emulator-only before/after profile. Clears the demo DB via test Harness.

Use an isolated Emulator owned by this run; never attach a user's shared DB.
--checkout selects an existing local checkout, never a remote project.
"""

import argparse
import hashlib
import json
import logging
import math
import os
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Lock, local
from unittest.mock import MagicMock
from uuid import uuid4


def summary(values):
    if not values:
        return None
    ordered = sorted(values)
    return {
        "count": len(values),
        "mean_ms": 1000 * sum(values) / len(values),
        "p50_ms": 1000 * ordered[math.ceil(len(values) * 0.5) - 1],
        "p95_ms": 1000 * ordered[math.ceil(len(values) * 0.95) - 1],
        "max_ms": 1000 * max(values),
    }


class MeasuredLock:
    def __init__(self, lock):
        self.lock, self.mutex, self.local = lock, Lock(), local()
        self.waits, self.holds = [], []

    def __enter__(self):
        before = time.perf_counter()
        self.lock.acquire()
        entered = time.perf_counter()
        with self.mutex:
            self.waits.append(entered - before)
        stack = getattr(self.local, "stack", [])
        stack.append(entered)
        self.local.stack = stack
        return self

    def __exit__(self, *args):
        try:
            held = time.perf_counter() - self.local.stack.pop()
            with self.mutex:
                self.holds.append(held)
        finally:
            self.lock.release()


class ErrorTypes(logging.Handler):
    def __init__(self):
        super().__init__()
        self.events = []

    def emit(self, record):
        if not record.exc_info:
            return
        error = record.exc_info[1]
        chain, lock_timeout = [], False
        while error is not None and len(chain) < 8:
            chain.append(type(error).__name__)
            lock_timeout |= "Transaction lock timeout" in str(error)
            error = error.__cause__
        self.events.append({"exception_types": chain, "transaction_lock_timeout": lock_timeout})


def measure_store(store):
    durations, mutex = [], Lock()
    admission = None
    if hasattr(store, "_transaction_lock"):
        admission = MeasuredLock(store._transaction_lock)
        store._transaction_lock = admission
    original = store.atomic

    def timed(callback):
        start = time.perf_counter()
        try:
            return original(callback)
        finally:
            with mutex:
                durations.append(time.perf_counter() - start)

    store.atomic = timed
    return durations, admission


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--require-correct", action="store_true")
    args = parser.parse_args()
    if os.environ.get("RUN_FIRESTORE_EMULATOR_TESTS") != "1":
        raise ValueError("Explicit isolated Emulator test mode required")
    if not 1 <= args.repeats <= 5:
        raise ValueError("Use 1..5 profile repetitions")
    root = args.checkout.resolve()
    sys.path.insert(0, str(root))
    from backend_a.runtime import localhost_endpoint
    from backend_a.store import FirestoreStore
    from tests.conftest import Harness

    localhost_endpoint(os.environ.get("FIRESTORE_EMULATOR_HOST", ""))
    if os.environ.get("ENABLE_CLOUD", "false").lower() != "false":
        raise ValueError("Cloud access forbidden")
    if (
        Path(sys.modules[FirestoreStore.__module__].__file__).resolve()
        != root / "backend_a/store.py"
    ):
        raise ValueError("Wrong source checkout imported")
    logging.getLogger().handlers = [logging.NullHandler()]
    capture = ErrorTypes()
    app_logger = logging.getLogger("api.app")
    app_logger.handlers, app_logger.propagate = [capture], False
    app_logger.setLevel(logging.ERROR)
    groups = []
    for _ in range(args.repeats):
        h = Harness()  # Clears demo-gesture-relay in the isolated local Emulator.
        try:
            h.start()
            h.complete("image_gen", 0)  # Fixture, not AI; isolate submission cost.
            capture.events.clear()
            durations, admission = measure_store(h.store)
            barrier = Barrier(8)
            path = f"/api/rounds/{h.round_id}/steps/1/submit"

            def send(index, barrier=barrier, h=h, path=path):
                if index < 8:
                    barrier.wait(timeout=10)
                start = time.perf_counter()
                response = h.client.post(
                    path,
                    headers={"Authorization": "Bearer local:a"},
                    json={"request_id": str(uuid4()), "text": "race"},
                )
                return response.status_code, time.perf_counter() - start

            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=8) as pool:
                responses = list(pool.map(send, range(12)))
            elapsed = time.perf_counter() - started
            statuses = Counter(status for status, _ in responses)
            group = {
                "statuses": dict(statuses),
                "elapsed_s": elapsed,
                "requests_per_s": 12 / elapsed,
                "response": summary([duration for _, duration in responses]),
                "atomic": summary(durations),
                "admission_wait": summary(admission.waits) if admission else None,
                "lock_hold": summary(admission.holds) if admission else None,
                "failure_types": list(capture.events),
            }
            group["correct"] = statuses == {202: 1, 409: 11} and h.doc()["current_step_index"] == 2
            groups.append(group)
            print(json.dumps({"group": len(groups), **group}), flush=True)
        finally:
            h.client.close()

    # Controlled independent/no-I/O callbacks show the head-of-line tradeoff.
    # These numbers are NOT Firestore/Cloud throughput estimates.
    from google.cloud import firestore

    original_decorator = firestore.transactional
    firestore.transactional = lambda fn: fn
    try:
        store = FirestoreStore(MagicMock())
        durations, admission = measure_store(store)
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: store.atomic(lambda tx: time.sleep(0.02)), range(24)))
        independent = {
            "kind": "synthetic_no_io_20ms_callbacks",
            "callbacks": 24,
            "workers": 8,
            "elapsed_s": time.perf_counter() - started,
            "atomic": summary(durations),
            "admission_wait": summary(admission.waits) if admission else None,
        }
    finally:
        firestore.transactional = original_decorator

    result = {
        "source_revision": subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
        ).strip(),
        "store_sha256": hashlib.sha256((root / "backend_a/store.py").read_bytes()).hexdigest(),
        "requests_per_group": 12,
        "concurrency": 8,
        "groups": groups,
        "correct_groups": sum(group["correct"] for group in groups),
        "independent_control": independent,
        "real_cloud": "unverified",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps({"output": str(args.output), "correct_groups": result["correct_groups"]}),
        flush=True,
    )
    if args.require_correct and result["correct_groups"] != args.repeats:
        raise AssertionError("Submission profile did not preserve one 202 / eleven 409 responses")


if __name__ == "__main__":
    main()
