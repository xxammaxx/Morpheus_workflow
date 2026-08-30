import importlib.util
from pathlib import Path


ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "workflow" / "v2" / "create_workflows_v2.py"


def load_setup():
    spec = importlib.util.spec_from_file_location("morpheus_setup", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fresh_install_uses_complete_canonical_run_schema(monkeypatch):
    setup = load_setup()
    calls = []

    def fake_api(method, path, body=None):
        calls.append((method, path, body))
        if method == "POST" and path == "/api/v1/data-tables":
            return 201, {"id": "runs"}
        if method == "GET" and path == "/api/v1/data-tables/runs/columns":
            return 200, [{"name": name} for name in setup.RUN_TABLE_REQUIRED_COLUMNS]
        raise AssertionError((method, path, body))

    monkeypatch.setattr(setup, "api", fake_api)
    table_id, columns = setup.migrate_runs_schema()

    assert table_id == "runs"
    assert set(columns) == set(setup.RUN_TABLE_REQUIRED_COLUMNS)
    create = calls[0][2]
    assert [column["name"] for column in create["columns"]] == setup.RUN_TABLE_REQUIRED_COLUMNS
    assert all(column["type"] == "string" for column in create["columns"])


def test_upgrade_adds_only_missing_columns_and_preserves_existing(monkeypatch):
    setup = load_setup()
    existing = set(setup.RUN_TABLE_REQUIRED_COLUMNS[:15])
    calls = []

    def fake_api(method, path, body=None):
        calls.append((method, path, body))
        if method == "POST" and path == "/api/v1/data-tables":
            return 409, {"message": "already exists"}
        if method == "GET" and path == "/api/v1/data-tables?limit=250":
            return 200, {"data": [{"id": "runs", "name": "autodev_runs"}]}
        if method == "GET" and path == "/api/v1/data-tables/runs/columns":
            return 200, [{"name": name} for name in existing]
        if method == "POST" and path == "/api/v1/data-tables/runs/columns":
            existing.add(body["name"])
            return 201, {"name": body["name"]}
        raise AssertionError((method, path, body))

    monkeypatch.setattr(setup, "api", fake_api)
    table_id, columns = setup.migrate_runs_schema()

    assert table_id == "runs"
    assert set(columns) == set(setup.RUN_TABLE_REQUIRED_COLUMNS)
    added = [body["name"] for method, path, body in calls if method == "POST" and path.endswith("/columns")]
    assert added == setup.RUN_TABLE_REQUIRED_COLUMNS[15:]
    assert not any(method == "DELETE" or method == "PATCH" and path.endswith("/columns") for method, path, _ in calls)


def test_upgrade_is_idempotent_when_schema_already_converged(monkeypatch):
    setup = load_setup()
    calls = []

    def fake_api(method, path, body=None):
        calls.append((method, path, body))
        if method == "POST" and path == "/api/v1/data-tables":
            return 409, {}
        if method == "GET" and path == "/api/v1/data-tables?limit=250":
            return 200, {"data": [{"id": "runs", "name": "autodev_runs"}]}
        if method == "GET" and path == "/api/v1/data-tables/runs/columns":
            return 200, [{"name": name} for name in setup.RUN_TABLE_REQUIRED_COLUMNS]
        raise AssertionError((method, path, body))

    monkeypatch.setattr(setup, "api", fake_api)
    setup.migrate_runs_schema()
    setup.migrate_runs_schema()

    assert not any(method == "POST" and path.endswith("/columns") for method, path, _ in calls)


def test_canonical_start_and_continuation_fields_are_in_schema():
    setup = load_setup()
    required = set(setup.RUN_TABLE_REQUIRED_COLUMNS)
    for field in (
        "project_id", "issue_number", "correlation_id", "source_run_id",
        "continuation_reason", "requested_action", "created_via", "requested_by",
    ):
        assert field in required

    generator = (ROOT / "workflow" / "v2" / "generate_workflows_v2.py").read_text()
    written_fields = {
        "run_id", "state", "task_ref", "repository_ref", "current_job", "decision",
        "reason_code", "created_at", "updated_at", "result_ref", "trace_id", "backend",
        "project_id", "issue_number", "correlation_id", "source_run_id",
        "continuation_reason", "requested_action", "created_via", "requested_by",
        "last_action", "excluded_model", "excluded_provider",
    }
    assert written_fields.issubset(required)
    assert all(field in generator for field in written_fields)
