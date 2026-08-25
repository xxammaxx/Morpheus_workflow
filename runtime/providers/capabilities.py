#!/usr/bin/env python3
"""Small persisted capability evidence registry."""

import json
import os
import tempfile
import re

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
                self.entries = json.load(stream).get("entries", {})
        except (OSError, ValueError):
            self.entries = {}

    def save(self):
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
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

    def get(self, provider, model):
        return self.entries.get("%s/%s" % (provider, model))
