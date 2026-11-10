"""Compatibility checks for the main snapshot; all cloud operations are stubbed."""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend_a.entrypoint import main, service_app
from backend_a.runtime import build_runtime
from backend_a.tasks import CloudTasks
from common.settings import Settings, get_settings
from common.storage import AssetError, LocalBlobStore

ROOT = Path(__file__).resolve().parent.parent


def test_b_settings_names_preserve_a_guards_and_provider_overrides(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("AI_MODE=real\nENABLE_CLOUD=true\n")
    monkeypatch.setenv("GCP_PROJECT", "demo-compatible")
    monkeypatch.setenv("STORAGE_BUCKET", "demo-assets")
    settings = get_settings()
    assert settings.gcp_project == settings.project_id == "demo-compatible"
    assert settings.storage_bucket == settings.bucket_name == "demo-assets"
    assert settings.ai_mode == "mock" and not settings.enable_cloud
    settings = Settings(ai_provider="developer", provider_image="vertex", gemini_api_key="secret")
    assert settings.provider_image == "vertex"
    assert settings.provider_read == settings.provider_embed == "developer"
    assert "secret" not in repr(settings)


def test_worker_composition_boots_offline_and_rejects_public_tasks(monkeypatch):
    import google.auth

    from api.worker import build_worker_app

    default = MagicMock(side_effect=AssertionError("must not discover credentials"))
    monkeypatch.setattr(google.auth, "default", default)
    with TestClient(build_worker_app(Settings())) as client:
        assert client.get("/health").json() == {"ok": True}
        assert client.post("/tasks/run", json={}).status_code == 401
        assert client.post("/api/rooms", json={}).status_code == 404
    assert service_app("api") == "api.main:app"
    assert service_app("worker") == "api.worker:app"
    assert service_app("deadlines") == "api.internal:app"
    with pytest.raises(ValueError):
        service_app("unknown")
    default.assert_not_called()


def test_canonical_b_task_path_uses_service_origin_as_oidc_audience():
    client = MagicMock()
    client.queue_path.return_value = "projects/demo/locations/local/queues/q"
    settings = Settings(
        worker_url="https://worker.example/tasks/run", tasks_service_account="test@example.com"
    )
    CloudTasks(client, settings).send("job", {"target": "worker", "payload": {}})
    request = client.create_task.call_args.kwargs["request"]
    assert request["task"]["http_request"]["oidc_token"]["audience"] == "https://worker.example"


@pytest.mark.parametrize(
    ("role", "cloud_run", "expected"),
    [("api", True, 16), ("api", False, 8), ("worker", True, 8), ("deadlines", True, 8)],
)
def test_uvicorn_leaves_headroom_for_cloud_run_api_connections(
    monkeypatch, role, cloud_run, expected
):
    monkeypatch.setenv("SERVICE_ROLE", role)
    monkeypatch.setenv("PORT", "8080")
    if cloud_run:
        monkeypatch.setenv("K_SERVICE", "test-service")
    else:
        monkeypatch.delenv("K_SERVICE", raising=False)
    run = MagicMock()
    monkeypatch.setattr("uvicorn.run", run)

    main()

    assert run.call_args.args == (service_app(role),)
    assert run.call_args.kwargs["limit_concurrency"] == expected


@pytest.mark.parametrize("host", ["production.example:9199", "http://127.0.0.1:9198"])
def test_emulator_storage_cannot_fall_back_to_remote_or_disagree(monkeypatch, host):
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8080")
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099")
    monkeypatch.setenv("FIREBASE_STORAGE_EMULATOR_HOST", "127.0.0.1:9199")
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", host)
    with pytest.raises(ValueError):
        build_runtime(Settings(runtime_mode="emulator"))


def test_legacy_local_storage_rejects_escape_and_symlinks(tmp_path):
    root = tmp_path / "assets"
    root.mkdir()
    (root / "link").symlink_to(tmp_path, target_is_directory=True)
    blobs = LocalBlobStore(root)
    for path in ("../escape", str(tmp_path / "absolute"), "link/escape"):
        with pytest.raises(AssetError):
            blobs.put(path, b"private", "image/png")
    assert not (tmp_path / "escape").exists()


def test_deploy_script_selects_persistent_worker_and_requires_explicit_settings(tmp_path):
    # A fake executable records arguments. No gcloud/Firebase executable or credentials used.
    recorder = tmp_path / "gcloud"
    recorder.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$CAPTURE"\n')
    recorder.chmod(0o755)
    capture = tmp_path / "args"
    env = {"PATH": f"{tmp_path}:/usr/bin:/bin", "CAPTURE": str(capture)}
    script = ROOT / "scripts/deploy_worker.sh"
    assert subprocess.run(["bash", str(script)], env=env, capture_output=True).returncode == 2
    assert not capture.exists()
    env["ENABLE_CLOUD"] = "true"
    assert subprocess.run(["bash", str(script)], env=env, capture_output=True).returncode == 2
    assert not capture.exists()
    env.update(
        {
            name: "test-only"
            for name in (
                "TASKS_LOCATION",
                "TASKS_QUEUE",
                "WORKER_URL",
                "DEADLINE_URL",
                "TASKS_SERVICE_ACCOUNT",
                "INTERNAL_AUDIENCE",
            )
        }
    )
    assert subprocess.run(["bash", str(script)], env=env, capture_output=True).returncode == 0
    args = capture.read_text()
    assert "SERVICE_ROLE=worker,RUNTIME_MODE=cloud,ENABLE_CLOUD=true" in args
    assert "--no-allow-unauthenticated" in args
    assert not os.environ.get("ENABLE_CLOUD")  # tests must never opt the parent process in
