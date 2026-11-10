from unittest.mock import Mock

import pytest

from backend_a.entrypoint import main


@pytest.mark.parametrize(
    ("mode", "override", "expected"),
    [
        (None, None, "127.0.0.1"),
        ("local", None, "127.0.0.1"),
        ("local", "192.0.2.5", "192.0.2.5"),
        ("emulator", None, "0.0.0.0"),
        ("cloud", "192.0.2.5", "0.0.0.0"),
    ],
)
def test_bind_host_matches_runtime_authentication(monkeypatch, mode, override, expected):
    for name in ("RUNTIME_MODE", "LOCAL_BIND_HOST"):
        monkeypatch.delenv(name, raising=False)
    if mode is not None:
        monkeypatch.setenv("RUNTIME_MODE", mode)
    if override is not None:
        monkeypatch.setenv("LOCAL_BIND_HOST", override)
    monkeypatch.setenv("ENABLE_CLOUD", str(mode == "cloud"))
    monkeypatch.setenv("AI_MODE", "mock")
    monkeypatch.setenv("PROJECT_ID", "demo-gesture-relay")
    monkeypatch.setenv("SERVICE_ROLE", "api")
    run = Mock()
    monkeypatch.setattr("uvicorn.run", run)

    main()

    assert run.call_args.kwargs["host"] == expected
