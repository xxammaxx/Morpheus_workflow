#!/usr/bin/env python3
"""Adapter-facing provider runtime facade."""

import os

from .catalog import ProviderCatalog
from .protocol import (
    NoEligibleProvider,
    ProviderExecution,
    ProviderFailure,
    ProviderRequest,
    RouteRequest,
    new_id,
)
from .router import ProviderRouter
from .lease import ProviderProbeLease


class ProviderRuntime:
    def __init__(self, catalog=None, enabled=None):
        self.enabled = (
            enabled
            if enabled is not None
            else os.environ.get("AUTODEV_FREE_FIRST_ENABLED", "true").lower()
            in {"1", "true", "yes", "on"}
        )
        self.catalog = catalog or ProviderCatalog()
        self.router = ProviderRouter(self.catalog)
        self._refreshed_runs = set()

    def begin_run(self, run_id):
        """Refresh OpenCode's live catalog once for the canonical run."""
        if not run_id or run_id in self._refreshed_runs:
            return None
        self._refreshed_runs.add(run_id)
        return self.catalog.refresh_live()

    def select(self, request):
        if not self.enabled:
            return None
        return self.router.select(request)

    def direct_invoke(self, decision, messages, task_class, timeout, attempt_id):
        adapter = self.catalog.adapters.get(decision.get("selected_provider"))
        if adapter is None:
            raise NoEligibleProvider("NO_ELIGIBLE_FREE_PROVIDER")
        if adapter.base_url.rstrip("/") != str(
            decision.get("route_endpoint", "")
        ).rstrip("/"):
            raise ProviderFailure("provider route endpoint mismatch")
        outbound_id = new_id("outbound")
        request = ProviderRequest(
            provider=decision["selected_provider"],
            model=decision["selected_model"],
            messages=messages,
            endpoint=decision.get("route_endpoint", ""),
            task_class=task_class,
            routing_event_id=decision.get("routing_event_id", ""),
            outbound_request_id=outbound_id,
        )
        response = adapter.invoke(
            request,
            timeout=timeout,
            probe_lease_id=decision.get("probe_lease_id"),
        )
        updated = self.router.record_execution(
            decision, response, outbound_id, attempt_id
        )
        proof = {
            "routing_event_id": updated["routing_event_id"],
            "attempt_id": attempt_id,
            "selected_provider": updated["selected_provider"],
            "selected_model": updated["selected_model"],
            "actual_provider": updated.get("actual_provider"),
            "actual_model": updated.get("actual_model"),
            "free_eligible": updated.get("free_eligible", False),
            "execution_proof": updated.get("execution_proof"),
            "usage": updated.get("usage", {}),
            "actual_cost": updated.get("actual_cost", 0),
            "failover": updated.get("fallback_chain", []),
        }
        return ProviderExecution(
            updated, response, updated.get("fallback_chain", []), attempt_id, proof
        )

    def acquire_probe_lease(self, provider, owner="morpheus-maintenance"):
        return ProviderProbeLease().acquire(provider, owner)

    def probe_once(self, provider, model, messages, task_class="research", timeout=60, owner="morpheus-maintenance"):
        lease = self.acquire_probe_lease(provider, owner)
        decision = self.router._decision(
            {
                "provider": provider,
                "model": model,
                "endpoint": self.catalog.adapters[provider].base_url,
                "cost_class": "LOCAL_ZERO_COST" if provider in {"ollama", "lmstudio"} else "FREE_HARD_STOP",
                "account_class": "local" if provider in {"ollama", "lmstudio"} else "verified-free-account",
            },
            RouteRequest(provider=provider, model=model, task_class=task_class),
            0,
        )
        decision["probe_lease_id"] = lease["lease_id"]
        try:
            result = self.direct_invoke(decision, messages, task_class, timeout, "probe-" + lease["lease_id"][:12])
        finally:
            ProviderProbeLease().release(lease["lease_id"])
        return result

    def invoke_with_failover(self, request, messages, task_class, timeout, attempt_id):
        if request.run_id:
            self.begin_run(request.run_id)
        decisions = self.router.candidates(request)
        if not decisions:
            raise NoEligibleProvider("NO_ELIGIBLE_FREE_PROVIDER")
        failures = []
        for decision in decisions:
            # Permit the one authorized provider probe lease to travel with
            # its candidate after an earlier provider fails in the same
            # semantic attempt. This is maintenance-only and provider-scoped.
            if decision.get("selected_provider") == os.environ.get(
                "AUTODEV_MAINTENANCE_PROBE_PROVIDER", ""
            ).strip():
                lease_id = os.environ.get(
                    "AUTODEV_MAINTENANCE_PROBE_LEASE_ID", ""
                ).strip()
                if lease_id:
                    decision["probe_lease_id"] = lease_id
            for attempt_number in range(1, 3):
                try:
                    execution = self.direct_invoke(
                        decision, messages, task_class, timeout, attempt_id
                    )
                    execution.failover_chain = failures
                    execution.decision["fallback_chain"] = failures
                    execution.execution_proof["failover"] = failures
                    execution.decision["attempt_number"] = attempt_number
                    return execution
                except ProviderFailure as exc:
                    status = getattr(exc, "status", None)
                    fatal = (not exc.retryable) or status in {401, 403, 404}
                    provider_wide = status in {401, 403}
                    self.router.record_transport_failure(
                        request.run_id,
                        decision["selected_provider"],
                        decision["selected_model"],
                        failure_class="TRANSPORT_FATAL" if fatal else "TRANSPORT",
                        fatal=fatal,
                        provider_wide=provider_wide,
                    )
                    failures.append(
                        {
                            "provider": decision["selected_provider"],
                            "model": decision["selected_model"],
                            "attempt_number": attempt_number,
                            "failure_class": "TRANSPORT_FATAL" if fatal else "TRANSPORT",
                            "failure": str(exc)[:120],
                            "next_model_reason": "MODEL_EXCLUDED" if fatal or attempt_number == 2 else "RETRY_SAME_MODEL",
                        }
                    )
                    if fatal or attempt_number == 2:
                        break
        raise NoEligibleProvider("NO_ELIGIBLE_FREE_PROVIDER")


def build_runtime():
    return ProviderRuntime()
