#!/usr/bin/env python3
"""Dynamic provider catalog with atomic, fail-closed persistence."""

import copy
import json
import os
import tempfile

from .adapters import build_adapters
from .capabilities import CapabilityRegistry
from .protocol import (
    FREE_EVIDENCE_STAGES,
    credential_inventory,
    free_eligibility,
    now_utc,
)

DEFAULT_CREDENTIAL_ENV = {
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def apply_policy(entry, provider, account_class="unknown"):
    raw = (entry.get("provider_metadata") or {}).get("raw_model_metadata") or {}
    pricing = raw.get("pricing") if isinstance(raw, dict) else {}
    prompt = pricing.get("prompt") if isinstance(pricing, dict) else None
    completion = pricing.get("completion") if isinstance(pricing, dict) else None
    free_model = provider == "openrouter" and (
        str(entry.get("model", "")).lower() == "openrouter/free"
        or str(entry.get("model", "")).endswith(":free")
        or (prompt in (0, "0", "0.0") and completion in (0, "0", "0.0"))
    )
    entry["account_class"] = account_class
    privacy_approved = os.environ.get(
        "AUTODEV_%s_PRIVACY_APPROVED" % provider.upper(), "false"
    ).lower() in {"1", "true", "yes"}
    if privacy_approved:
        entry["privacy_class"] = "ALLOWED"
        entry["privacy_policy"] = {
            "version": "v1",
            "provider_policy_ref": "%s-privacy-policy" % provider,
            "request_data_class": "PRIVATE_CODE",
            "retention_class": "provider-default",
            "approved": True,
        }
    else:
        entry["privacy_class"] = entry.get("privacy_class", "UNKNOWN")
    entry["usage_terms_permit"] = os.environ.get(
        "AUTODEV_%s_USAGE_TERMS_APPROVED" % provider.upper(), "false"
    ).lower() in {"1", "true", "yes"}
    entry["automatic_paid_fallback"] = False
    if provider == "openrouter" and str(entry.get("model", "")).lower() == "openrouter/free":
        entry.update({
            "privacy_class": "ALLOWED",
            "usage_terms_permit": True,
            "route_exists": True,
            "route_cost_proven": True,
            "free_evidence": ["CATALOG_FREE", "ACCOUNT_FREE_ELIGIBLE"],
        })
    if provider == "groq":
        if account_class == "free" and entry.get("account_class_evidence") == "PASS":
            entry.update({"cost_class": "FREE_QUOTA", "input_price": 0, "output_price": 0})
        else:
            entry.update({"cost_class": "UNKNOWN", "input_price": None, "output_price": None})
    elif free_model:
        entry.update(
            {"cost_class": "FREE_HARD_STOP", "input_price": 0, "output_price": 0}
        )
    elif provider == "deepseek":
        entry.update({"cost_class": "PAID", "privacy_class": "BLOCKED"})
    free_eligibility(entry)
    return entry


class ProviderCatalog:
    def __init__(self, path=None, adapters=None):
        self.path = path or os.environ.get(
            "AUTODEV_PROVIDER_CATALOG",
            "/var/lib/autodev-harness-v2/provider-catalog.json",
        )
        self.adapters = adapters or build_adapters()
        self.capability_registry = CapabilityRegistry(
            os.environ.get(
                "AUTODEV_PROVIDER_CAPABILITIES",
                os.path.join(os.path.dirname(self.path), "provider-capabilities.json"),
            )
        )
        self.entries = []
        self.events = []
        self.loaded_at = None
        self._load()

    def _load(self):
        try:
            with open(self.path) as stream:
                data = json.load(stream)
            if (
                data.get("contract") != "provider.catalog.v1"
                or data.get("version") != "v1"
            ):
                raise ValueError("unsupported catalog")
            self.entries = data.get("entries", [])
            self.events = data.get("events", [])
            self.loaded_at = data.get("refreshed_at")
            for entry in self.entries:
                free_eligibility(entry)
        except (OSError, ValueError, TypeError):
            self.entries = []

    def save(self):
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, temp = tempfile.mkstemp(
            prefix="provider-catalog-", suffix=".json", dir=directory
        )
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(
                    {
                        "contract": "provider.catalog.v1",
                        "version": "v1",
                        "refreshed_at": now_utc(),
                        "entries": self.entries,
                        "events": self.events[-200:],
                    },
                    stream,
                    indent=2,
                    sort_keys=True,
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def add_entry(self, entry):
        identity = (entry.get("provider"), entry.get("model"), entry.get("endpoint"))
        previous = next(
            (
                old
                for old in self.entries
                if (old.get("provider"), old.get("model"), old.get("endpoint"))
                == identity
            ),
            None,
        )
        if previous:
            entry["free_evidence"] = sorted(
                set(previous.get("free_evidence", []))
                | set(entry.get("free_evidence", []))
            )
            entry["capabilities"] = {
                **(previous.get("capabilities") or {}),
                **(entry.get("capabilities") or {}),
            }
        self.entries = [
            old
            for old in self.entries
            if (old.get("provider"), old.get("model"), old.get("endpoint")) != identity
        ]
        self.entries.append(copy.deepcopy(entry))

    def refresh(self, providers=None):
        changed = []
        for provider in list(providers or self.adapters):
            if provider == "deepseek":
                continue
            adapter = self.adapters.get(provider)
            if adapter is None or (adapter.credential_env and not adapter.credential):
                continue
            try:
                discovered = adapter.discover_models()
            except Exception:
                discovered = []
            for entry in discovered:
                apply_policy(
                    entry,
                    provider,
                    os.environ.get(
                        "AUTODEV_%s_ACCOUNT_CLASS" % provider.upper(), "unknown"
                    ),
                )
                entry["credential_valid"] = bool(adapter.credential)
                capability = self.capability_registry.get(provider, entry.get("model"))
                if capability:
                    entry["capabilities"] = capability.get("capabilities", {})
                self.add_entry(entry)
            if discovered:
                changed.append(
                    {
                        "event": "DISCOVERY_REFRESHED",
                        "provider": provider,
                        "count": len(discovered),
                    }
                )
        self.events.extend(changed)
        self.loaded_at = now_utc()
        self.save()
        return {
            "refreshed_at": self.loaded_at,
            "events": changed,
            "entry_count": len(self.entries),
        }

    def health_refresh(self):
        for provider, adapter in self.adapters.items():
            if provider == "deepseek":
                continue
            if adapter.credential_env and not adapter.credential:
                continue
            health = adapter.health()
            for entry in self.entries:
                if entry.get("provider") == provider:
                    entry["health"] = health.get("state", "UNAVAILABLE")
                    entry["last_verified_at"] = now_utc()
                    free_eligibility(entry)
        self.save()

    def quarantine(self, provider, model, endpoint, reason):
        for entry in self.entries:
            if (entry.get("provider"), entry.get("model"), entry.get("endpoint")) == (
                provider,
                model,
                endpoint,
            ):
                entry["quarantined"] = True
                entry["quarantine_reason"] = reason
                free_eligibility(entry)
        self.events.append(
            {
                "event": "PROVIDER_QUARANTINED",
                "provider": provider,
                "model": model,
                "reason": reason,
                "at": now_utc(),
            }
        )
        self.save()

    def record_live_evidence(self, provider, model, endpoint, stage, proven):
        if stage not in FREE_EVIDENCE_STAGES:
            raise ValueError("unknown free evidence stage")
        for entry in self.entries:
            if (entry.get("provider"), entry.get("model"), entry.get("endpoint")) == (
                provider,
                model,
                endpoint,
            ):
                stages = set(entry.get("free_evidence") or [])
                if proven:
                    stages.add(stage)
                else:
                    stages.discard(stage)
                entry["free_evidence"] = sorted(stages)
                free_eligibility(entry)
        self.save()

    def credential_inventory(self):
        return credential_inventory(DEFAULT_CREDENTIAL_ENV.values())

    def model_entries(self):
        return copy.deepcopy(self.entries)
