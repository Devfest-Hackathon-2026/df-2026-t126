"""Select API or private Worker from the same image; no cloud action at import."""

import logging
import os

from common.settings import get_settings


def service_app(role: str) -> str:
    apps = {"api": "api.main:app", "worker": "api.worker:app", "deadlines": "api.internal:app"}
    if role not in apps:
        raise ValueError("SERVICE_ROLE must be api, worker or deadlines")
    return apps[role]


def main():
    import uvicorn

    role = os.environ.get("SERVICE_ROLE", "api")
    target = service_app(role)
    # Cloud Run's API deployment caps in-flight requests at 8. Uvicorn
    # also counts idle keep-alive connections, so leave room for those.
    limit_concurrency = 16 if role == "api" and os.environ.get("K_SERVICE") else 8
    logging.basicConfig(level=logging.INFO)
    host = "0.0.0.0"
    if get_settings().runtime_mode == "local":
        host = os.environ.get("LOCAL_BIND_HOST") or "127.0.0.1"
    uvicorn.run(
        target,
        host=host,
        port=int(os.environ.get("PORT", "8080")),
        limit_concurrency=limit_concurrency,
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
