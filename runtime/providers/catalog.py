#!/usr/bin/env python3
"""Dynamic provider catalog with atomic, fail-closed persistence."""

import copy
import json
import os
import tempfile
import urllib.parse

from .adapters import build_adapters
from .capabilities import CapabilityRegistry, normalize_live_capabilities
from .opencode import authenticated_api_key_providers, discover_auth_file, load_auth_file, refresh_catalog
from .protocol import (
    FREE_EVIDENCE_STAGES,
    credential_inventory,
    free_eligibility,
    now_utc,
    is_deepseek_identifier,
)

DEFAULT_CREDENTIAL_ENV = {
    "openai": "OPENAI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}
LOCAL_PROVIDERS = {"ollama", "lmstudio"}

def apply_policy(entry, provider, account_class="unknown"):
    if is_deepseek_identifier(provider, entry.get("model")):
        entry.update({
            "catalog_eligible": False,
            "router_eligible": False,
            "explicit_request_allowed": False,
            "fallback_allowed": False,
            "opencode_default": False,
            "free_eligible": False,
            "automatic_paid_fallback": False,
            "privacy_class": "BLOCKED",
        })
        return free_eligibility(entry)
    raw = (entry.get("provider_metadata") or {}).get("raw_model_metadata") or {}
    pricing = raw.get("pricing") if isinstance(raw, dict) else {}
    prompt = pricing.get("prompt") if isinstance(pricing, dict) else None
    completion = pricing.get("completion") if isinstance(pricing, dict) else None
    explicit_zero = prompt in (0, "0", "0.0") and completion in (0, "0", "0.0")
    route_zero = entry.get("route_cost_proven") is True and entry.get("cost_class") in {
        "FREE_HARD_STOP", "LOCAL_ZERO_COST", "FREE_QUOTA"
    }
    entry["zero_cost_verified"] = bool(
        entry.get("zero_cost_verified") is True or explicit_zero or route_zero
    )
    if explicit_zero or route_zero:
        entry["free_evidence"] = sorted(
            set(entry.get("free_evidence") or []) | {"CATALOG_FREE"}
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
    endpoint = str(entry.get("endpoint", ""))
    parsed = urllib.parse.urlparse(endpoint)
    trusted_endpoints = {
        value.strip().rstrip("/")
        for value in os.environ.get(
            "AUTODEV_LOCAL_ZERO_COST_TRUSTED_ENDPOINTS",
            "http://127.0.0.1:11434/v1,http://127.0.0.1:1234/v1",
        ).split(",")
        if value.strip()
    }
    trusted_local = (
        provider in {"ollama", "lmstudio"}
        and parsed.scheme in {"http", "https"}
        and endpoint.rstrip("/") in trusted_endpoints
    )
    if trusted_local:
        entry.update({
            "account_class": "local",
            "account_class_evidence": "PASS",
            "cost_class": "LOCAL_ZERO_COST",
            "zero_cost_verified": True,
            "input_price": 0,
            "output_price": 0,
            "privacy_class": "ALLOWED",
            "usage_terms_permit": True,
            "route_exists": True,
            "route_cost_proven": True,
            "automatic_paid_fallback": False,
            "free_evidence": ["CATALOG_FREE", "ACCOUNT_FREE_ELIGIBLE"],
        })
    if provider == "openrouter" and (
        str(entry.get("model", "")).lower() == "openrouter/free"
        or str(entry.get("model", "")).lower().endswith(":free")
    ):
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
    elif explicit_zero and entry["zero_cost_verified"]:
        entry.update(
            {"cost_class": "FREE_HARD_STOP", "input_price": 0, "output_price": 0}
        )
    elif provider == "deepseek":
        entry.update({"cost_class": "PAID", "privacy_class": "BLOCKED"})
    entry["authenticated"] = bool(entry.get("authenticated", True))
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
        self.catalog_version = None
        self.authenticated_providers = set()
        self.auth_inventory_known = False
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
            self.catalog_version = data.get("catalog_version")
            self.authenticated_providers = set(data.get("authenticated_providers") or [])
            self.auth_inventory_known = data.get("auth_inventory_known", False)
            for entry in self.entries:
                if is_deepseek_identifier(entry.get("provider"), entry.get("model")):
                    apply_policy(entry, entry.get("provider"), entry.get("account_class", "unknown"))
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
                        "catalog_version": self.catalog_version,
                        "authenticated_providers": sorted(self.authenticated_providers),
                        "auth_inventory_known": self.auth_inventory_known,
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
            if "embed" in str(entry.get("model", "")).lower():
                entry["capabilities"] = {}
            for key in (
                "probe_attempted",
                "promoted_free_eligible",
                "execution_proof",
                "selection_to_execution_proven",
                "actual_cost_proof",
                "actual_cost",
                "actual_provider",
                "actual_model",
                "resolved_model",
                "tool_probe",
                "vision_probe",
                "structured_output_score",
                "structured_output_probe",
            ):
                if key in previous:
                    entry[key] = previous[key]
        self.entries = [
            old
            for old in self.entries
            if (old.get("provider"), old.get("model"), old.get("endpoint")) != identity
        ]
        self.entries.append(copy.deepcopy(entry))

    def refresh(self, providers=None, authenticated_providers=None):
        if authenticated_providers is not None:
            self.authenticated_providers = set(authenticated_providers)
        changed = []
        for provider in list(providers or self.adapters):
            if provider == "deepseek":
                continue
            if (
                self.auth_inventory_known
                and provider not in self.authenticated_providers
                and provider not in LOCAL_PROVIDERS
            ):
                continue
            adapter = self.adapters.get(provider)
            if adapter is None or (adapter.credential_env and not adapter.credential):
                continue
            try:
                discovered = adapter.discover_models()
            except Exception:
                discovered = []
            for entry in discovered:
                if provider in LOCAL_PROVIDERS:
                    # A successful authoritative local model discovery is
                    # also a live health check for that local endpoint.
                    entry["health"] = "HEALTHY"
                apply_policy(
                    entry,
                    provider,
                    os.environ.get(
                        "AUTODEV_%s_ACCOUNT_CLASS" % provider.upper(), "unknown"
                    ),
                )
                entry["credential_valid"] = (
                    True if not adapter.credential_env else bool(adapter.credential)
                )
                entry["authenticated"] = (
                    not self.auth_inventory_known
                    or provider in self.authenticated_providers
                    or provider in LOCAL_PROVIDERS
                )
                capability = self.capability_registry.get(provider, entry.get("model"))
                if capability:
                    entry["capabilities"] = capability.get("capabilities", {})
                normalize_live_capabilities(entry)
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

    def refresh_live(self, auth_file=None, opencode_bin=None, cwd=None):
        """Refresh OpenCode's live catalog before provider enrichment.

        The CLI refresh is mandatory in the live path, but an unavailable
        local binary does not erase the last catalog snapshot.  Selection
        remains fail-closed because stale entries still need current free and
        capability evidence.
        """
        auth_path = discover_auth_file(
            auth_file or os.environ.get("AUTODEV_OPENCODE_AUTH_FILE")
        )
        authenticated = set()
        if auth_path:
            authenticated = authenticated_api_key_providers(load_auth_file(auth_path))
        self.auth_inventory_known = True
        for entry in self.entries:
            entry["authenticated"] = bool(
                entry.get("provider") in LOCAL_PROVIDERS
                or (auth_path and entry.get("provider") in authenticated)
            )
            free_eligibility(entry)
        report = {"refresh": "FAILED", "catalog_entries": 0}
        try:
            live = refresh_catalog(
                opencode_bin
                or os.environ.get("AUTODEV_OPENCODE_CATALOG_BIN")
                or os.environ.get("OPENCODE_BIN", "opencode"),
                cwd=cwd,
            )
            report = {"refresh": "PASS", "catalog_entries": len(live["entries"])}
            self.catalog_version = now_utc()
            for raw in live["entries"]:
                provider = raw.get("provider")
                if provider not in self.adapters or is_deepseek_identifier(provider, raw.get("model")):
                    continue
                if (
                    self.auth_inventory_known
                    and provider not in authenticated
                    and provider not in LOCAL_PROVIDERS
                ):
                    continue
                model = raw.get("model")
                endpoint = self.adapters[provider].base_url
                pricing = raw.get("pricing") or {}
                entry = {
                    "provider": provider,
                    "model": model,
                    "endpoint": endpoint,
                    "availability": True,
                    "health": "HEALTHY",
                    "account_class": "opencode-api-key",
                    "authenticated": provider in authenticated or provider in LOCAL_PROVIDERS,
                    "provider_metadata": {"raw_model_metadata": raw},
                    "input_price": pricing.get("prompt"),
                    "output_price": pricing.get("completion"),
                    "capabilities": raw.get("capabilities") or {},
                    "context_length": raw.get("context_length", raw.get("context_window", 0)),
                    "route_exists": True,
                    "route_cost_proven": pricing.get("prompt") in (0, "0", "0.0") and pricing.get("completion") in (0, "0", "0.0"),
                }
                apply_policy(entry, provider, "opencode-api-key")
                if (
                    entry.get("authenticated") is True
                    and entry.get("route_cost_proven") is True
                    and entry.get("cost_class") == "FREE_HARD_STOP"
                ):
                    entry["free_evidence"] = sorted(
                        set(entry.get("free_evidence") or [])
                        | {"ACCOUNT_FREE_ELIGIBLE"}
                    )
                    free_eligibility(entry, require_execution=False)
                normalize_live_capabilities(entry)
                self.add_entry(entry)
            # OpenCode's global catalog may omit local providers even when
            # the configured local adapter exposes a current authoritative
            # model list. Reconcile those providers separately.
            self.refresh(
                providers=LOCAL_PROVIDERS,
                authenticated_providers=authenticated,
            )
            self.authenticated_providers = authenticated
            self.events.append({"event": "OPENCODE_LIVE_REFRESH", **report, "at": now_utc()})
            self.save()
        except (OSError, ValueError, RuntimeError, TypeError):
            self.events.append({"event": "OPENCODE_LIVE_REFRESH_FAILED", "at": now_utc()})
            self.save()
        return report

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
