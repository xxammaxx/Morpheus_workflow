#!/usr/bin/env python3
"""Small fail-closed maintenance lease for one provider probe.

The state is deliberately provider-scoped and contains no credentials.  A
state file is used so an adapter restart cannot silently turn an active probe
into ordinary traffic: a lease is stale until explicitly re-established.
"""

import json
import os
import tempfile
import time
import uuid


class ProbeLeaseError(RuntimeError):
    pass


class ProviderProbeLease:
    def __init__(self, path=None, ttl=120, clock=None):
        self.path = path or os.environ.get(
            "AUTODEV_PROVIDER_PROBE_LEASE",
            "/var/lib/autodev-harness-v2/provider-probe-lease.json",
        )
        self.ttl = min(120, max(1, int(ttl)))
        self.clock = clock or time.time

    def _load(self):
        try:
            with open(self.path) as stream:
                value = json.load(stream)
            if not isinstance(value, dict):
                return None
            return value
        except (OSError, ValueError, TypeError):
            return None

    def _save(self, value):
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix="provider-lease-", dir=directory)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as stream:
                json.dump(value, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def _active(self):
        value = self._load()
        if not value:
            return None
        if value.get("expires_at", 0) <= self.clock():
            return None
        if value.get("remaining_probe_requests") != 1:
            return value
        return value

    def acquire(self, provider, owner):
        if provider in {"deepseek"} or provider not in {"openrouter", "groq", "ollama", "lmstudio"}:
            raise ProbeLeaseError("PROVIDER_NOT_PROBE_ELIGIBLE")
        active = self._active()
        if active:
            raise ProbeLeaseError("PROVIDER_PROBE_LEASE_ACTIVE")
        now = self.clock()
        lease = {
            "provider": provider,
            "mode": "exclusive_probe",
            "lease_id": uuid.uuid4().hex,
            "owner": str(owner),
            "expires_at": now + self.ttl,
            "remaining_probe_requests": 1,
        }
        self._save(lease)
        return dict(lease)

    def authorize(self, provider, lease_id):
        lease = self._active()
        if not lease or lease.get("provider") != provider:
            raise ProbeLeaseError("PROVIDER_PROBE_LEASE_REQUIRED")
        if lease.get("lease_id") != lease_id:
            raise ProbeLeaseError("PROVIDER_PROBE_LEASE_ID_INVALID")
        if lease.get("remaining_probe_requests") != 1:
            raise ProbeLeaseError("PROVIDER_PROBE_LEASE_EXHAUSTED")
        lease["remaining_probe_requests"] = 0
        self._save(lease)
        return lease

    def check_ordinary(self, provider):
        lease = self._active()
        if lease and lease.get("provider") == provider:
            raise ProbeLeaseError("PROVIDER_PROBE_LEASE_ACTIVE")

    def release(self, lease_id):
        lease = self._load()
        if lease and lease.get("lease_id") == lease_id:
            self._save({"state": "released", "released_at": self.clock()})

