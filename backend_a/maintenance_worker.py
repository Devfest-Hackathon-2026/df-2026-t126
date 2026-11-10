"""Private stdin-only child entry. No server, loop, or AI; one recovery pass."""

import json
import sys

from backend_a.maintenance import maintenance_once
from backend_a.runtime import build_runtime
from common.settings import Settings


def main():
    settings = Settings(**json.load(sys.stdin))
    if settings.runtime_mode != "cloud" or not settings.enable_cloud or settings.ai_mode != "mock":
        raise ValueError("An explicitly enabled cloud maintenance runtime is required")
    runtime = build_runtime(settings)
    maintenance_once(runtime.game)


if __name__ == "__main__":
    main()
