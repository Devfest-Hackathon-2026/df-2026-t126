"""Killable, one-shot maintenance for deployed Cloud runtimes.

SDK retries cannot be reliably cancelled by cancelling a Python thread. A fresh
interpreter owns the clients and is killed/reaped by subprocess.run on timeout.
No key or access token is forwarded; deployed identity uses the runtime SA.
"""

import json
import logging
import os
import subprocess
import sys

from backend_a.errors import ApiError

logger = logging.getLogger(__name__)
MAINTENANCE_TIMEOUT_SECONDS = 150
FORWARDED_SETTINGS = (
    "runtime_mode",
    "enable_cloud",
    "project_id",
    "bucket_name",
    "tasks_location",
    "tasks_queue",
    "worker_url",
    "deadline_url",
    "tasks_service_account",
    "internal_audience",
    "asset_ttl_hours",
    "ai_timeout_s",
    "max_attempts",
    "deadline_grace_s",
    "dropout_after_s",
    "text_max_length",
    "video_max_bytes",
    "json_max_bytes",
    "gesture_batch_max_bytes",
    "allowed_video_types",
    "heartbeat_interval_s",
    "join_attempt_limit",
    "join_attempt_window_s",
)
FORWARDED_ENV = (
    "PATH",
    "LANG",
    "LC_ALL",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONUNBUFFERED",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "FIRESTORE_EMULATOR_HOST",
    "FIREBASE_AUTH_EMULATOR_HOST",
    "STORAGE_EMULATOR_HOST",
    "FIREBASE_STORAGE_EMULATOR_HOST",
)


def run_cloud_maintenance(settings):
    if settings.runtime_mode != "cloud" or not settings.enable_cloud:
        raise ValueError("Subprocess maintenance requires an explicitly enabled cloud runtime")
    payload = {key: getattr(settings, key) for key in FORWARDED_SETTINGS}
    payload["ai_mode"] = "mock"  # Maintenance never constructs an AI client.
    env = {key: os.environ[key] for key in FORWARDED_ENV if key in os.environ}
    try:
        subprocess.run(
            [sys.executable, "-m", "backend_a.maintenance_worker"],
            input=json.dumps(payload),
            text=True,
            env=env,
            stdout=subprocess.DEVNULL,
            check=True,
            timeout=MAINTENANCE_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError) as exc:
        logger.warning(
            "Maintenance child failed; durable checkpoints retained (%s)", type(exc).__name__
        )
        raise ApiError("INTERNAL", 500, "保守処理を完了できませんでした") from exc
