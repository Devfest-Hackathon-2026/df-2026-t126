#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${G1_PYTHON:?Explicit local Python executable required}"
: "${FRONTEND_ROOT:?Explicit frontend checkout required}"
node --test tools/emulator/rules.test.mjs
RUN_FIRESTORE_EMULATOR_TESTS=1 "$G1_PYTHON" -m pytest -q
RUN_PR3_LOCAL_VALIDATION=1 node tools/validate_frontend.mjs
