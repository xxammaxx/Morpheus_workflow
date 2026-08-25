"""OpenCode auth schema and live catalog parsing tests."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.opencode import (  # noqa: E402
    authenticated_api_key_providers,
    auth_identities,
    parse_catalog_output,
)
from providers.capabilities import normalize_live_capabilities  # noqa: E402


def test_auth_kinds_are_distinguished_without_exposing_values():
    document = {
        "zen": {"type": "api", "key": "fixture-api-value"},
        "github": {"type": "oauth", "access_token": "fixture-oauth-value"},
        "subscription": {"type": "subscription", "session": "fixture-session-value"},
        "unknown": {"value": "opaque"},
    }
    identities = {item.provider: item.kind for item in auth_identities(document)}
    assert identities == {
        "zen": "API_KEY",
        "github": "OAUTH",
        "subscription": "SUBSCRIPTION_SESSION",
        "unknown": "UNKNOWN",
    }
    assert authenticated_api_key_providers(document) == {"zen"}
    assert "fixture-api-value" not in json.dumps([{"provider": key} for key in identities])


def test_catalog_parser_accepts_machine_readable_json_lines():
    output = "\n".join([
        json.dumps({"provider": "zen", "id": "model-a", "pricing": {"prompt": 0, "completion": 0}}),
        json.dumps({"models": [{"provider": "zen", "id": "model-b"}]}),
    ])
    entries = parse_catalog_output(output)
    assert {(entry["provider"], entry["model"]) for entry in entries} == {
        ("zen", "model-a"), ("zen", "model-b")
    }


def test_human_catalog_rows_do_not_prove_free_status():
    assert parse_catalog_output("zen/model-a  free\n") == []


def test_live_opencode_capabilities_are_conservative_and_machine_readable():
    entry = {
        "provider_metadata": {
            "raw_model_metadata": {
                "capabilities": {
                    "toolcall": True,
                    "input": {"image": True},
                },
                "limit": {"context": 200000},
            }
        }
    }
    normalize_live_capabilities(entry)
    assert entry["capabilities"]["TOOL_CAPABLE"] is True
    assert entry["capabilities"]["VISION_CAPABLE"] is True
    assert entry["capabilities"]["LONG_CONTEXT_CAPABLE"] is True
