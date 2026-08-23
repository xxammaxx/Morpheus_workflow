#!/usr/bin/env python3
"""Canonical free-first route selection and proof recording."""

import copy
import os

from .protocol import (
    FREE_CLASSES,
    NoEligibleProvider,
    ProviderFailure,
    RouteRequest,
    TASK_CAPABILITIES,
    free_eligibility,
    probe_eligibility,
    promotion_eligibility,
    is_deepseek_identifier,
    new_id,
    now_utc,
)

AUTOMATIC_PAID_AGENT_ESCALATION = False


class ProviderRouter:
    def __init__(self, catalog, max_failover=None):
        configured = (
            max_failover
            if max_failover is not None
            else os.environ.get("AUTODEV_PROVIDER_FAILOVER_MAX", "3")
        )
        try:
            configured = int(configured)
        except (TypeError, ValueError):
            configured = 3
        self.catalog = catalog
        self.max_failover = max(1, configured)

    @staticmethod
    def _caps(request):
        required = list(request.requested_capabilities or [])
        capability = TASK_CAPABILITIES.get(request.task_class)
        if capability and capability not in required:
            required.append(capability)
        return required

    def _candidate_rows(self, request):
        rows = []
        for original in self.catalog.model_entries():
            entry = copy.deepcopy(original)
            if (
                request.model
                and request.provider == entry.get("provider")
                and entry.get("model") != request.model
            ):
                continue
            if is_deepseek_identifier(entry.get("provider"), entry.get("model")):
                continue
            if entry.get("quarantined") or entry.get("availability") is not True:
                continue
            if entry.get("health") not in ("HEALTHY", "DEGRADED"):
                continue
            if not all(
                (entry.get("capabilities") or {}).get(name) is True
                for name in self._caps(request)
            ):
                continue
            is_free = promotion_eligibility(entry) or probe_eligibility(entry)
            if not is_free:
                continue
            if entry.get("cost_class") not in FREE_CLASSES:
                continue
            rows.append(entry)
        return rows

    def _decision(self, entry, request, rank, fallback_chain=None):
        return {
            "contract": "provider.routing-decision.v1",
            "version": "v1",
            "routing_event_id": new_id("route"),
            "selected_provider": entry["provider"],
            "selected_model": entry["model"],
            "route_provider": entry["provider"],
            "route_model": entry["model"],
            "route_endpoint": entry["endpoint"],
            "route_account_class": entry.get("account_class"),
            "cost_class": entry.get("cost_class"),
            "free_eligible": True,
            "task_class": request.task_class,
            "routing_reason": "FREE_ELIGIBLE_CAPABILITY_HEALTH_QUOTA",
            "routing_rank": rank,
            "fallback_chain": fallback_chain or [],
            "paid_escalation": False,
            "expected_cost": 0.0,
            "execution_proof": "NOT_PROVEN",
            "probe_attempted": False,
            "selection_to_execution_proven": False,
            "actual_cost_proof": None,
            "selected_at": now_utc(),
        }

    def select(self, request):
        rows = self._candidate_rows(request)
        if not rows:
            raise NoEligibleProvider("NO_ELIGIBLE_FREE_PROVIDER")
        rows.sort(
            key=lambda entry: (
                0 if entry["provider"] == request.provider else 1,
                0 if entry["provider"] == "groq" else 1,
                entry.get("provider", ""),
                entry.get("model", ""),
            )
        )
        return self._decision(rows[0], request, 0)

    def candidates(self, request):
        rows = self._candidate_rows(request)
        rows.sort(
            key=lambda entry: (
                0 if entry["provider"] == request.provider else 1,
                0 if entry["provider"] == "groq" else 1,
                entry.get("provider", ""),
                entry.get("model", ""),
            )
        )
        return [
            self._decision(entry, request, index)
            for index, entry in enumerate(rows[: self.max_failover])
        ]

    def record_execution(self, decision, response, outbound_request_id, attempt_id):
        updated = copy.deepcopy(decision)
        updated["outbound_request_id"] = outbound_request_id
        updated["provider_request_id"] = response.provider_request_id
        updated["resolved_model"] = response.resolved_model
        updated["actual_provider"] = response.actual_provider or response.provider
        updated["actual_model"] = (
            response.actual_model
        )
        updated["usage"] = response.usage
        updated["actual_cost"] = response.actual_cost
        updated["attempt_id"] = attempt_id
        updated["probe_attempted"] = True
        entry = next((e for e in self.catalog.entries if
                      e.get("provider") == updated.get("selected_provider") and
                      e.get("model") == updated.get("selected_model") and
                      e.get("endpoint") == updated.get("route_endpoint")), {})
        if response.actual_cost is not None:
            updated["actual_cost_proof"] = "EXPLICIT_ZERO" if response.actual_cost == 0 else "EXPLICIT_NONZERO"
        elif entry.get("cost_class") == "FREE_HARD_STOP" and entry.get("input_price") == 0 and entry.get("output_price") == 0 and entry.get("automatic_paid_fallback") is False:
            updated["actual_cost_proof"] = "CATALOG_HARD_ZERO"
        else:
            updated["actual_cost_proof"] = "UNKNOWN"
        if response.actual_cost not in (None, 0, 0.0) or updated["actual_cost_proof"] == "UNKNOWN":
            self.catalog.quarantine(
                updated["selected_provider"],
                updated["selected_model"],
                updated["route_endpoint"],
                "UNEXPECTED_BILLABLE_USAGE",
            )
            raise ProviderFailure("UNEXPECTED_BILLABLE_USAGE")
        provider_ok = updated["selected_provider"] == updated["actual_provider"]
        dynamic_route = updated["selected_provider"] == "openrouter" and updated["selected_model"] == "openrouter/free"
        model_ok = bool(updated["actual_model"]) if dynamic_route else updated["selected_model"] == updated["actual_model"]
        updated["selection_to_execution_proven"] = bool(provider_ok and model_ok and (not dynamic_route or updated["resolved_model"]))
        updated["execution_proof"] = "PASS" if updated["selection_to_execution_proven"] else "NOT_PROVEN"
        updated["free_eligible"] = updated["execution_proof"] == "PASS"
        if updated["execution_proof"] == "PASS" and updated["actual_cost_proof"] in {"EXPLICIT_ZERO", "USAGE_ZERO", "CATALOG_HARD_ZERO"}:
            for catalog_entry in self.catalog.entries:
                if (catalog_entry.get("provider"), catalog_entry.get("model"), catalog_entry.get("endpoint")) == (updated.get("selected_provider"), updated.get("selected_model"), updated.get("route_endpoint")):
                    catalog_entry.update({"probe_attempted": True, "promoted_free_eligible": True, "execution_proof": "PASS", "selection_to_execution_proven": True, "actual_cost_proof": updated["actual_cost_proof"], "actual_cost": response.actual_cost})
                    break
        return updated
