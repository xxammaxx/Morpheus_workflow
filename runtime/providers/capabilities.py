#!/usr/bin/env python3
"""Small persisted capability evidence registry."""

import json
import os
import tempfile
import re
import datetime as dt
import fcntl

from .protocol import now_utc

CAPABILITY_NAMES = (
    "RESEARCH_CAPABLE",
    "PLAN_CAPABLE",
    "BUILD_CAPABLE",
    "REVIEW_CAPABLE",
    "TOOL_CAPABLE",
    "VISION_CAPABLE",
    "STRUCTURED_OUTPUT_CAPABLE",
    "LONG_CONTEXT_CAPABLE",
)

DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60
TOOL_CONTRACT_VERSION = "morpheus-tool-contract-v1"
EMPIRICAL_CAPABILITY_FIELDS = {
    "BUILD_CAPABLE",
    "TOOL_CAPABLE",
    "STRUCTURED_OUTPUT_CAPABLE",
}


def _contains_visual_input(value):
    if isinstance(value, dict):
        mime = str(value.get("mime_type", value.get("mimeType", ""))).lower()
        if mime.startswith("image/") or mime in {"application/pdf", "image"}:
            return True
        if value.get("vision") is True or value.get("requires_vision") is True:
            return True
        return any(_contains_visual_input(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_visual_input(child) for child in value)
    text = str(value or "").lower()
    return bool(re.search(r"\b(screenshot|photograph|photo|diagram|camera frame|visual pdf|ui screenshot|image|jpeg|png|webp|scanned page|visual layout|board|pcb)\b", text))


def classify_task(task, task_class=None):
    """Return hard requirements; visual pixels always imply vision."""
    task = task if isinstance(task, dict) else {"description": task}
    task_class = task_class or task.get("task_class") or task.get("job_type") or "research"
    task_class = str(task_class).split(".", 1)[0]
    description = " ".join(str(value) for value in task.values() if isinstance(value, (str, int, float)))
    build = task_class in {"build", "fix"} or bool(task.get("requires_repository_tools"))
    plan = task_class == "plan" or bool(task.get("requires_structured_output"))
    profile = {
        "requires_text": True,
        "requires_reasoning": task_class in {"research", "plan", "review", "verify"},
        "requires_code": build,
        "requires_repository_tools": build,
        "requires_structured_output": plan or bool(task.get("strict_json")),
        "requires_function_tools": bool(task.get("requires_function_tools")),
        "requires_vision": _contains_visual_input(task),
        "requires_long_context": bool(task.get("requires_long_context")),
        "minimum_context_tokens": int(task.get("minimum_context_tokens") or 0),
        "task_complexity": str(task.get("task_complexity") or ("high" if build or plan else "normal")),
        "task_class": task_class,
    }
    profile["vision_reason"] = "visual_input_detected" if profile["requires_vision"] else None
    return profile


def normalize_live_capabilities(entry):
    """Map provider metadata into conservative hard-gate booleans."""
    raw = (entry.get("provider_metadata") or {}).get("raw_model_metadata") or {}
    architecture = raw.get("architecture") if isinstance(raw, dict) else {}
    modalities = architecture.get("input_modalities", []) if isinstance(architecture, dict) else []
    parameters = raw.get("supported_parameters", []) if isinstance(raw, dict) else []
    live_capabilities = raw.get("capabilities") if isinstance(raw, dict) else {}
    if not isinstance(live_capabilities, dict):
        live_capabilities = {}
    live_input = live_capabilities.get("input", {}) if isinstance(live_capabilities, dict) else {}
    live_limit = raw.get("limit") if isinstance(raw, dict) else {}
    live_output = live_capabilities.get("output", {}) if isinstance(live_capabilities, dict) else {}
    model_identity = " ".join(
        str(raw.get(name, "")) for name in ("id", "name", "family")
    ).lower()
    caps = dict(entry.get("capabilities") or {})
    caps["VISION_CAPABLE"] = bool(
        caps.get("VISION_CAPABLE") is True
        or entry.get("supports_vision") is True
        or "image" in {str(value).lower() for value in modalities}
        or live_input.get("image") is True
    )
    caps["TOOL_CAPABLE"] = bool(
        caps.get("TOOL_CAPABLE") is True
        or entry.get("supports_tools") is True
        or any(str(value).lower() in {"tools", "tool_choice", "function_calling"} for value in parameters)
        or live_capabilities.get("toolcall") is True
    )
    text_capable = live_input.get("text") is True and live_output.get("text") is True
    reasoning_capable = live_capabilities.get("reasoning") is True
    caps["RESEARCH_CAPABLE"] = bool(
        caps.get("RESEARCH_CAPABLE") is True or (text_capable and reasoning_capable)
    )
    caps["PLAN_CAPABLE"] = bool(
        caps.get("PLAN_CAPABLE") is True or (text_capable and reasoning_capable)
    )
    caps["REVIEW_CAPABLE"] = bool(
        caps.get("REVIEW_CAPABLE") is True or (text_capable and reasoning_capable)
    )
    caps["BUILD_CAPABLE"] = bool(
        caps.get("BUILD_CAPABLE") is True
        or (
            text_capable
            and caps.get("TOOL_CAPABLE") is True
            and any(token in model_identity for token in ("code", "coder", "coding", "developer"))
        )
    )
    caps["STRUCTURED_OUTPUT_CAPABLE"] = bool(
        caps.get("STRUCTURED_OUTPUT_CAPABLE") is True
        or raw.get("supports_structured_output") is True
        or any(str(value).lower() in {"response_format", "json_schema"} for value in parameters)
    )
    context = (
        entry.get("context_length")
        or raw.get("context_length")
        or raw.get("context_window")
        or (live_limit.get("context") if isinstance(live_limit, dict) else 0)
        or 0
    )
    caps["LONG_CONTEXT_CAPABLE"] = bool(context and int(context) >= 32768)
    entry["supports_vision"] = caps["VISION_CAPABLE"]
    entry["capabilities"] = caps
    return entry


def _parse_timestamp(value):
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def evidence_identity(provider, model, evidence, expected_probe_version=None):
    identity = evidence.get("identity") or {}
    return {
        "provider": identity.get("provider", evidence.get("provider")),
        "model": identity.get("model", evidence.get("model")),
        "probe_version": evidence.get("probe_version"),
        "tool_contract_version": identity.get(
            "tool_contract_version", evidence.get("tool_contract_version")
        ),
    } == {
        "provider": provider,
        "model": model,
        "probe_version": expected_probe_version or evidence.get("probe_version"),
        "tool_contract_version": TOOL_CONTRACT_VERSION,
    }


def merge_empirical_capabilities(entry, evidence, now=None, ttl_seconds=None,
                                 expected_probe_version=None):
    """Merge only fresh, identity-matching probe evidence into a live entry."""
    now = now or dt.datetime.now(dt.timezone.utc)
    ttl_seconds = int(ttl_seconds or os.environ.get(
        "AUTODEV_PROVIDER_CAPABILITY_TTL_SECONDS", DEFAULT_TTL_SECONDS
    ))
    verified_at = evidence.get("verified_at")
    verified = _parse_timestamp(verified_at)
    age = (now - verified).total_seconds() if verified else None
    identity_match = evidence_identity(
        entry.get("provider"), entry.get("model"), evidence, expected_probe_version
    )
    fresh = age is not None and age >= 0 and age < ttl_seconds
    passed = evidence.get("probe_status", evidence.get("passed")) == "PASS"
    valid = bool(identity_match and fresh and passed)
    if valid:
        for name, value in (evidence.get("capabilities") or {}).items():
            if name in EMPIRICAL_CAPABILITY_FIELDS and value is True:
                entry.setdefault("capabilities", {})[name] = True
        entry["capability_evidence"] = {
            "provider": entry.get("provider"),
            "model": entry.get("model"),
            "probe_version": evidence.get("probe_version"),
            "tool_contract_version": TOOL_CONTRACT_VERSION,
            "verified_at": verified_at,
            "expires_at": (verified + dt.timedelta(seconds=ttl_seconds)).isoformat(),
            "evidence_hash": evidence.get("evidence_hash"),
        }
        entry["capability_status"] = "PROVEN"
        entry["capability_needs_reprobe"] = False
    else:
        entry["capability_status"] = "NEEDS_REPROBE"
        entry["capability_needs_reprobe"] = True
        entry["capability_invalidation_reason"] = (
            "IDENTITY_MISMATCH" if not identity_match else
            "EXPIRED" if not fresh else "PROBE_NOT_PASS"
        )
        for name in EMPIRICAL_CAPABILITY_FIELDS:
            entry.setdefault("capabilities", {})[name] = False
    return {
        "valid": valid,
        "identity_match": identity_match,
        "fresh": fresh,
        "needs_reprobe": not valid,
        "ttl_seconds": ttl_seconds,
    }


class CapabilityRegistry:
    def __init__(self, path=None):
        self.path = path or os.environ.get(
            "AUTODEV_PROVIDER_CAPABILITIES",
            "/var/lib/autodev-harness-v2/provider-capabilities.json",
        )
        self.entries = {}
        self._load()

    def _load(self):
        try:
            with open(self.path) as stream:
                document = json.load(stream)
            entries = document.get("entries", {})
            self.entries = entries if isinstance(entries, dict) else {}
        except (OSError, ValueError, TypeError, AttributeError):
            self.entries = {}

    def save(self):
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        lock_path = self.path + ".lock"
        with open(lock_path, "a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                # Preserve entries written by a concurrent probe/refresh.
                try:
                    with open(self.path) as stream:
                        document = json.load(stream)
                    existing = document.get("entries", {})
                    if isinstance(existing, dict):
                        for key, value in existing.items():
                            if key not in self.entries:
                                self.entries[key] = value
                except (OSError, ValueError, TypeError, AttributeError):
                    pass
                fd, temp = tempfile.mkstemp(prefix="provider-capabilities-", dir=directory)
                try:
                    with os.fdopen(fd, "w") as stream:
                        json.dump(
                            {
                                "contract": "provider.model-capability.v1",
                                "version": "v1",
                                "entries": self.entries,
                            },
                            stream,
                            sort_keys=True,
                        )
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temp, self.path)
                finally:
                    if os.path.exists(temp):
                        os.unlink(temp)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def record(self, provider, model, capabilities, stage, passed, evidence=""):
        key = "%s/%s" % (provider, model)
        current = self.entries.setdefault(
            key,
            {
                "provider": provider,
                "model": model,
                "capabilities": {name: False for name in CAPABILITY_NAMES},
                "stages": {},
            },
        )
        current["stages"][stage] = {
            "passed": bool(passed),
            "evidence": evidence[:200],
            "verified_at": now_utc(),
        }
        for name, value in capabilities.items():
            if name in CAPABILITY_NAMES:
                current["capabilities"][name] = bool(value) and bool(passed)
        self.save()
        return current

    def record_probe(self, provider, model, capabilities, probe_version,
                     tool_contract_version=TOOL_CONTRACT_VERSION,
                     passed=True, evidence_hash="", verified_at=None):
        verified_at = verified_at or now_utc()
        payload = {
            "provider": provider,
            "model": model,
            "capabilities": {
                name: bool(value) for name, value in capabilities.items()
                if name in EMPIRICAL_CAPABILITY_FIELDS
            },
            "probe_status": "PASS" if passed else "FAIL",
            "probe_version": probe_version,
            "tool_contract_version": tool_contract_version,
            "verified_at": verified_at,
            "evidence_hash": evidence_hash,
            "identity": {
                "provider": provider,
                "model": model,
                "tool_contract_version": tool_contract_version,
            },
        }
        current = self.entries.setdefault(
            "%s/%s" % (provider, model),
            {"provider": provider, "model": model, "capabilities": {}, "stages": {}},
        )
        current["provider"] = provider
        current["model"] = model
        current["capabilities"] = {
            **(current.get("capabilities") or {}), **payload["capabilities"]
        }
        current["probe_version"] = probe_version
        current["tool_contract_version"] = tool_contract_version
        current["probe_status"] = payload["probe_status"]
        current["verified_at"] = verified_at
        current["evidence_hash"] = evidence_hash
        current["identity"] = payload["identity"]
        current["stages"]["BUILD_TOOL_PROBE"] = {
            "passed": bool(passed), "evidence": evidence_hash[:200],
            "verified_at": verified_at,
        }
        self.save()
        return current

    def get(self, provider, model):
        return self.entries.get("%s/%s" % (provider, model))
