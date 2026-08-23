#!/usr/bin/env python3
"""Small persisted capability evidence registry."""

import json
import os
import tempfile

from .protocol import now_utc

CAPABILITY_NAMES = (
    "RESEARCH_CAPABLE",
    "PLAN_CAPABLE",
    "BUILD_CAPABLE",
    "REVIEW_CAPABLE",
    "TOOL_CAPABLE",
)


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
