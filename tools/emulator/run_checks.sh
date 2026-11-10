#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
# Called by `firebase emulators:exec --project demo-gesture-relay` only.
node --test tools/emulator/rules.test.mjs
RUN_FIRESTORE_EMULATOR_TESTS=1 .venv/bin/python -m pytest -q
