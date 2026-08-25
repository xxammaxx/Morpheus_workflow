#!/usr/bin/env python3
"""Canonical free-first route selection and proof recording."""

import copy
import os
from .capabilities import classify_task, normalize_live_capabilities
from .session import RunRoutingState

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
    def __init__(self, catalog, max_failover=None, state=None):
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
        self.state = state or RunRoutingState()
        self.semantic_threshold = max(1, int(os.environ.get("MAX_SEMANTIC_FAILURES_PER_MODEL_PER_TASK", "2")))
        self.run_demotion_threshold = max(1, int(os.environ.get("MAX_DISTINCT_TASK_FAILURES_BEFORE_RUN_DEMOTION", "3")))

    @staticmethod
    def _caps(request):
        required = list(request.requested_capabilities or [])
        capability = TASK_CAPABILITIES.get(request.task_class)
        if capability and capability not in required:
            required.append(capability)
        profile = request.task_profile or {}
        if profile.get("requires_code") and "BUILD_CAPABLE" not in required:
            required.append("BUILD_CAPABLE")
        if profile.get("requires_vision") and "VISION_CAPABLE" not in required:
            required.append("VISION_CAPABLE")
        if profile.get("requires_repository_tools") and "TOOL_CAPABLE" not in required:
            required.append("TOOL_CAPABLE")
        if profile.get("requires_structured_output") and "STRUCTURED_OUTPUT_CAPABLE" not in required:
            required.append("STRUCTURED_OUTPUT_CAPABLE")
        return required

    def _candidate_rows(self, request):
        rows = []
        state = self.state.load(request.run_id) if request.run_id else RunRoutingState.empty("")
        excluded = set(request.excluded_models or []) | set(state["run_model_exclusions"])
        task_excluded = set(state["task_model_exclusions"].get(request.task_id, set())) if request.task_id else set()
        for original in self.catalog.model_entries():
            entry = copy.deepcopy(original)
            normalize_live_capabilities(entry)
            identity = "%s/%s" % (entry.get("provider"), entry.get("model"))
            if (
                request.model
                and request.provider == entry.get("provider")
                and entry.get("model") != request.model
            ):
                continue
            if is_deepseek_identifier(entry.get("provider"), entry.get("model")):
                continue
            if identity in excluded or identity in task_excluded:
                continue
            if entry.get("provider") in state["provider_exclusions"]:
                continue
            if entry.get("authenticated") is False:
                continue
            if entry.get("quarantined") or entry.get("availability") is not True:
                continue
            if entry.get("health") not in ("HEALTHY", "DEGRADED"):
                continue
            if not all((entry.get("capabilities") or {}).get(name) is True for name in self._caps(request)):
                continue
            profile = request.task_profile or classify_task({"task_class": request.task_class}, request.task_class)
            caps = entry.get("capabilities") or {}
            if profile.get("requires_vision") and (
                not caps.get("VISION_CAPABLE") or entry.get("vision_probe") == "FAIL"
            ):
                continue
            if profile.get("requires_repository_tools") and (
                not caps.get("TOOL_CAPABLE") or entry.get("tool_probe") != "PASS"
            ):
                continue
            if profile.get("requires_structured_output") and (
                not caps.get("STRUCTURED_OUTPUT_CAPABLE")
                or float(entry.get("structured_output_score") or 0) < 0.8
            ):
                continue
            if profile.get("requires_long_context") and int(entry.get("context_length") or 0) < int(profile.get("minimum_context_tokens") or 0):
                continue
            is_free = promotion_eligibility(entry) or probe_eligibility(entry)
            if not is_free:
                continue
            if entry.get("cost_class") not in FREE_CLASSES:
                continue
            entry["_rank_score"] = self._rank_score(entry, request, state)
            rows.append(entry)
        return rows

    @staticmethod
    def _rank_score(entry, request, state):
        """Score evidence, never a source-code model/provider order."""
        score = float(entry.get("score") or 0)
        score += float(entry.get("historical_success_rate") or 0) * 100
        score += float(entry.get("task_class_success", {}).get(request.task_class, 0) or 0) * 100
        score += float(entry.get("tool_success_rate") or 0) * 25 if request.task_profile.get("requires_repository_tools") else 0
        score += float(entry.get("structured_output_success") or 0) * 25 if request.task_profile.get("requires_structured_output") else 0
        score += float(entry.get("vision_success") or 0) * 25 if request.task_profile.get("requires_vision") else 0
        score -= float(entry.get("recent_failures") or 0) * 10
        score -= float(entry.get("latency_ms") or 0) / 100000
        return score

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
            "task_id": request.task_id,
            "required_capabilities": self._caps(request),
            "task_capability_profile": request.task_profile or {},
            "routing_reason": "FREE_ELIGIBLE_CAPABILITY_HEALTH_QUOTA",
            "selection_reason": "LIVE_ZERO_COST_CAPABILITY_SCORE",
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
        rows.sort(key=lambda entry: (-entry["_rank_score"], entry.get("provider", ""), entry.get("model", "")))
        decision = self._decision(rows[0], request, 0)
        if request.run_id:
            self.state.record(request.run_id, selection={
                "task_id": request.task_id,
                "task_class": request.task_class,
                "provider": decision["selected_provider"],
                "model": decision["selected_model"],
                "reason": decision["selection_reason"],
            })
        return decision

    def candidates(self, request):
        rows = self._candidate_rows(request)
        rows.sort(key=lambda entry: (-entry["_rank_score"], entry.get("provider", ""), entry.get("model", "")))
        return [
            self._decision(entry, request, index)
            for index, entry in enumerate(rows[: self.max_failover])
        ]

    def record_transport_failure(self, run_id, provider, model, failure_class="TRANSPORT", fatal=False, provider_wide=False):
        if not run_id:
            return
        identity = "%s/%s" % (provider, model)
        state = self.state.load(run_id)
        count = int(state["model_transport_failure_count"].get(identity, 0)) + 1
        event = {
            "model_transport_failure_count": {identity: count},
            "model_last_failure_class": {identity: failure_class},
        }
        if fatal or count >= 2:
            event["run_model_exclusions"] = [identity]
        if provider_wide:
            event["provider_exclusions"] = [provider]
        self.state.record(run_id, **event)

    def record_semantic_failure(self, run_id, task_id, provider, model, verified=True):
        if not run_id or not verified:
            return False
        identity = "%s/%s" % (provider, model)
        key = "%s|%s" % (task_id, identity)
        state = self.state.load(run_id)
        count = int(state["model_semantic_failure_count"].get(key, 0)) + 1
        event = {"model_semantic_failure_count": {key: count}, "model_last_failure_class": {identity: "SEMANTIC"}}
        if count >= self.semantic_threshold:
            event["task_model_exclusions"] = {task_id: [identity]}
        tasks = set(state["distinct_task_failures"].get(identity, set()))
        tasks.add(str(task_id))
        if len(tasks) >= self.run_demotion_threshold:
            event["distinct_task_failures"] = {identity: sorted(tasks)}
            event["run_model_exclusions"] = [identity]
        self.state.record(run_id, **event)
        return count >= self.semantic_threshold

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
        elif entry.get("cost_class") in {"FREE_HARD_STOP", "LOCAL_ZERO_COST"} and entry.get("input_price") == 0 and entry.get("output_price") == 0 and entry.get("automatic_paid_fallback") is False:
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
                    stages = set(catalog_entry.get("free_evidence") or [])
                    stages.update({"DIRECT_LIVE_PROVEN", "ADAPTER_LIVE_PROVEN", "SELECTION_TO_EXECUTION_PROVEN"})
                    if catalog_entry.get("provider") == "openrouter" and catalog_entry.get("model") == "openrouter/free":
                        stages.update({"CATALOG_FREE", "ACCOUNT_FREE_ELIGIBLE"})
                    catalog_entry.update({"probe_attempted": True, "promoted_free_eligible": True, "execution_proof": "PASS", "selection_to_execution_proven": True, "actual_cost_proof": updated["actual_cost_proof"], "actual_cost": response.actual_cost, "free_evidence": sorted(stages)})
                    free_eligibility(catalog_entry)
                    self.catalog.save()
                    break
        return updated
