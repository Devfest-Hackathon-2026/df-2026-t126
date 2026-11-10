"""Transactional outbox delivery. Cloud Tasks administration belongs to B.

Only message delivery is implemented here. No queue creation, IAM or deployment.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


class MemoryTasks:
    def __init__(self):
        self.messages = {}

    def send(self, task_id, message):
        self.messages.setdefault(task_id, message)


class CloudTasks:
    def __init__(self, client, settings):
        self.client, self.settings = client, settings

    def send(self, task_id, message):
        from google.api_core.exceptions import AlreadyExists
        from google.cloud import tasks_v2
        from google.protobuf.timestamp_pb2 import Timestamp

        s = self.settings
        url = s.worker_url if message["target"] == "worker" else s.deadline_url
        if not url.startswith("https://") or not s.tasks_service_account:
            raise ValueError("HTTPS task target and OIDC service account are required")
        parent = self.client.queue_path(s.project_id, s.tasks_location, s.tasks_queue)
        task = {
            "name": f"{parent}/tasks/{task_id}",
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": url,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(message["payload"]).encode(),
                "oidc_token": {
                    "service_account_email": s.tasks_service_account,
                    "audience": f"{urlsplit(url).scheme}://{urlsplit(url).netloc}",
                },
            },
        }
        if message.get("schedule_at"):
            stamp = Timestamp()
            at = message["schedule_at"]
            stamp.FromDatetime(datetime.fromisoformat(at) if isinstance(at, str) else at)
            task["schedule_time"] = stamp
        try:
            self.client.create_task(request={"parent": parent, "task": task})
        except AlreadyExists:
            pass


OUTBOX = "task_outbox"
LEGACY_SCAN = "outbox_maintenance/legacy_schema"
SENT_RETENTION_S = 600
LEGACY_RESCAN_INTERVAL = timedelta(days=1)


def _scan_legacy(tx, limit, now):
    """Process a page of older records whose missing fields cannot be queried."""
    state = tx.get(LEGACY_SCAN) or {}
    if state.get("next_scan_at", now) > now:
        return
    docs = tx.select(OUTBOX, limit, after=state.get("after"))
    for key, doc in docs:
        if doc.get("sent") and not doc.get("sent_at"):
            tx.delete(f"{OUTBOX}/{key}")
        elif doc.get("sent") is None:
            doc["sent"] = False
            tx.set(f"{OUTBOX}/{key}", doc)
    # An older revision can still write legacy records during a rollout.
    next_state = (
        {"after": docs[-1][0]}
        if len(docs) == limit
        else {"next_scan_at": now + LEGACY_RESCAN_INTERVAL}
    )
    tx.set(LEGACY_SCAN, next_state)


def purge_sent_outbox(store, limit=100):
    if limit <= 0:
        return
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=SENT_RETENTION_S)

    def work(tx):
        expired = tx.select(OUTBOX, limit, where=("sent_at", "<", cutoff))
        # Current writers only set sent_at together with sent=True.
        # Leave the remainder of the cleanup budget for legacy records.
        if len(expired) < limit:
            _scan_legacy(tx, limit - len(expired), now)
        for key, doc in expired:
            if doc.get("sent"):
                tx.delete(f"{OUTBOX}/{key}")

    try:
        store.atomic(work)
    except Exception:
        logger.exception("Sent outbox purge failed; will retry on the next pass")


def dispatch_outbox(store, sender, limit=100):
    if limit <= 0:
        return
    try:
        pending = store.atomic(lambda tx: tx.select(OUTBOX, limit, where=("sent", "==", False)))
    except Exception:
        logger.exception("Outbox read failed; retained for retry")
        return
    for task_id, message in pending:
        try:
            sender.send(task_id, message)
        except Exception:
            logger.exception(
                "Task delivery failed; persisted for retry", extra={"task_id": task_id}
            )
            continue

        def mark(tx, task_id=task_id):
            path = f"{OUTBOX}/{task_id}"
            doc = tx.get(path)
            if doc and not doc.get("sent"):
                doc["sent"] = True
                doc["sent_at"] = datetime.now(UTC)
                tx.set(path, doc)

        try:
            store.atomic(mark)
        except Exception:
            logger.exception("Task sent but outbox acknowledgement failed; retry is idempotent")
