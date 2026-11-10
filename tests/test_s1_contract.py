import re
from pathlib import Path

from api.app import create_app


def test_fourteen_api_routes_and_success_statuses_match_s1_specification(h):
    spec = (Path(__file__).resolve().parent.parent / "docs/specification.md").read_text()
    table = spec.split("## 3. API 一覧", 1)[1].split("### 3-1.", 1)[0]
    entries = re.findall(r"\|\s*\d+\s*\|\s*`(GET|POST) ([^`]+)`.*?\|\s*(\d{3})\s*\|", table)
    assert len(entries) == 14
    actual = {
        (method, route.path): route.status_code or 200
        for route in create_app(h.runtime).routes
        if route.path.startswith("/api/")
        for method in route.methods
    }
    assert actual == {(method, path): int(status) for method, path, status in entries}


def test_openapi_documents_actual_400_envelope_instead_of_fastapi_default_422(h):
    schema = create_app(h.runtime).openapi()
    for path, methods in schema["paths"].items():
        if not path.startswith("/api/"):
            continue
        for operation in methods.values():
            assert "422" not in operation["responses"]
            if "400" in operation["responses"]:
                error = operation["responses"]["400"]["content"]["application/json"]["schema"]
                assert error["properties"]["error"]["required"] == ["code", "message"]
