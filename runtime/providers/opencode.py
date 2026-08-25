#!/usr/bin/env python3
"""OpenCode auth and live catalog helpers.

This module deliberately treats OpenCode's auth file as an opaque credential
store.  Only provider ids and auth kinds leave the process; secret values are
never returned by the reporting helpers.
"""

import json
import os
import subprocess
from dataclasses import dataclass


AUTH_KINDS = {"API_KEY", "OAUTH", "SUBSCRIPTION_SESSION", "UNKNOWN"}


@dataclass(frozen=True)
class AuthIdentity:
    provider: str
    kind: str


def _provider_records(document):
    if not isinstance(document, dict):
        return {}
    records = document.get("providers")
    if isinstance(records, dict):
        return records
    # Current OpenCode auth.json is provider-id keyed.  Ignore metadata keys
    # if a future schema adds them beside the provider records.
    return {
        key: value for key, value in document.items()
        if isinstance(value, dict) and key not in {"version", "metadata"}
    }


def classify_auth_record(record):
    if not isinstance(record, dict):
        return "UNKNOWN"
    kind = str(record.get("type", record.get("kind", ""))).lower()
    if kind in {"api", "api_key", "apikey", "key"} and isinstance(record.get("key"), str):
        return "API_KEY"
    if kind in {"oauth", "oauth2"} or any(
        isinstance(record.get(name), str) for name in ("access_token", "refresh_token")
    ):
        return "OAUTH"
    if kind in {"subscription", "subscription_session", "session"} or any(
        name in record for name in ("session", "session_token", "cookies")
    ):
        return "SUBSCRIPTION_SESSION"
    return "UNKNOWN"


def load_auth_file(path):
    with open(path, encoding="utf-8") as stream:
        document = json.load(stream)
    if not isinstance(document, dict):
        raise ValueError("OpenCode auth store must be an object")
    return document


def auth_identities(document):
    return [
        AuthIdentity(provider=str(provider), kind=classify_auth_record(record))
        for provider, record in sorted(_provider_records(document).items())
    ]


def authenticated_api_key_providers(document):
    return {
        identity.provider
        for identity in auth_identities(document)
        if identity.kind == "API_KEY"
    }


def discover_auth_file(explicit=None, user=None, home=None):
    candidates = []
    if explicit:
        candidates.append(os.path.expanduser(explicit))
    if home:
        candidates.append(os.path.join(home, ".local", "share", "opencode", "auth.json"))
    if user:
        try:
            import pwd
            candidates.append(os.path.join(pwd.getpwnam(user).pw_dir, ".local", "share", "opencode", "auth.json"))
        except (KeyError, ImportError):
            pass
    candidates.append(os.path.expanduser("~/.local/share/opencode/auth.json"))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return os.path.realpath(candidate)
    return None


def _json_values(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _json_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _json_values(child)


def parse_catalog_output(output):
    """Extract model metadata from JSON or JSON-lines CLI output.

    Human-readable rows are intentionally not promoted to free routes because
    they do not prove pricing or capabilities.  Provider adapters may still
    enrich those identities from their authoritative machine-readable APIs.
    """
    objects = []
    for line in str(output or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            objects.extend(_json_values(json.loads(line)))
        except (TypeError, ValueError):
            continue
    entries = []
    for obj in objects:
        models = obj.get("models") if isinstance(obj, dict) else None
        if isinstance(models, list):
            objects.extend(item for item in models if isinstance(item, dict))
        provider = obj.get("provider") or obj.get("provider_id")
        model = obj.get("id") or obj.get("model") or obj.get("model_id")
        if not provider and isinstance(model, str) and "/" in model:
            provider, model = model.split("/", 1)
        if not provider or not model:
            continue
        entry = dict(obj)
        entry.update({"provider": str(provider), "model": str(model)})
        entries.append(entry)
    unique = {}
    for entry in entries:
        unique[(entry["provider"], entry["model"])] = entry
    return list(unique.values())


def refresh_catalog(binary="opencode", cwd=None, timeout=30):
    """Run the live OpenCode catalog refresh and return metadata only."""
    try:
        result = subprocess.run(
            [binary, "models", "--refresh", "--verbose"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("OPENCODE_CATALOG_REFRESH_FAILED") from exc
    if result.returncode != 0:
        raise RuntimeError("OPENCODE_CATALOG_REFRESH_FAILED")
    return {
        "entries": parse_catalog_output(result.stdout),
        "stderr_present": bool(result.stderr.strip()),
        "returncode": result.returncode,
    }


def safe_catalog_report(entries):
    return [
        {
            "provider": entry.get("provider"),
            "model": entry.get("model"),
            "pricing": entry.get("pricing"),
            "capabilities": entry.get("capabilities"),
        }
        for entry in entries
    ]
