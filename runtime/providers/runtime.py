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
        response = adapter.invoke(request, timeout=timeout)
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

    def invoke_with_failover(self, request, messages, task_class, timeout, attempt_id):
        decisions = self.router.candidates(request)
        if not decisions:
            raise NoEligibleProvider("NO_ELIGIBLE_FREE_PROVIDER")
        failures = []
        for decision in decisions:
            try:
                execution = self.direct_invoke(
                    decision, messages, task_class, timeout, attempt_id
                )
                execution.failover_chain = failures
                execution.decision["fallback_chain"] = failures
                execution.execution_proof["failover"] = failures
                return execution
            except ProviderFailure as exc:
                if not exc.retryable or exc.uncertain:
                    raise
                failures.append(
                    {
                        "provider": decision["selected_provider"],
                        "model": decision["selected_model"],
                        "failure": exc.__class__.__name__,
                    }
                )
        raise NoEligibleProvider("NO_ELIGIBLE_FREE_PROVIDER")


def build_runtime():
    return ProviderRuntime()
