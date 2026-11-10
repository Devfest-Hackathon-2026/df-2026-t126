import hashlib
import json
import re
from pathlib import Path

from common.models import ErrorInfo, JobDoc, JobPayload, JobResult

ROOT = Path(__file__).resolve().parent.parent


# Only these integration entry points are pinned. The remaining hashes in the
# manifest document import provenance, not a freeze on B's prompts or AI tuning.
CONTRACT_SOURCES = ("worker/handler.py", "worker/jobs.py", "worker/main.py")


def test_b_integration_entry_points_match_recorded_origin():
    manifest = json.loads((ROOT / "docs/backend-b-source.json").read_text())
    assert re.fullmatch(r"[0-9a-f]{40}", manifest["revision"])
    for path in CONTRACT_SOURCES:
        expected = manifest["files"][path]
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path


def test_job_contracts_match_b_models_without_changing_shared_interface():
    manifest = json.loads((ROOT / "docs/backend-b-source.json").read_text())
    for model in (JobPayload, JobResult, JobDoc, ErrorInfo):
        assert model.model_json_schema() == manifest["job_schemas"][model.__name__]
