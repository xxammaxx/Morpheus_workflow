#!/usr/bin/env python3
"""HAMH evolution sandbox (ADR H12) — propose/test ONLY. Promotion is denied.

Hard governance constants (order section 18):

    EVOLVER_CAN_PROPOSE      = YES
    EVOLVER_CAN_TEST         = YES
    EVOLVER_CAN_PROMOTE      = NO
    EVOLVER_CAN_CHANGE_GATES = NO
    EVOLVER_CAN_CHANGE_HOLDOUT = NO

A model NEVER modifies its own ACTIVE harness directly. The only allowed path
is: production trajectories -> weakness mining -> hypothesis -> minimal
candidate modification -> candidate -> evaluation -> regression -> holdout ->
shadow -> canary -> AUTHORIZED promotion.

Guards implemented here:
  - one component per experiment (no multi-change candidates)
  - leakage sentinel between candidate material and the HOLDOUT set
  - matched-compute control verdict (A/B/C)
  - weakness mining requires aggregated evidence (>= MIN_EVIDENCE_RUNS)
"""

import hashlib
import re

from . import registry as _registry_mod
from .deepseek_adapter import (
    EVOLUTION_REASONING_EFFORTS as _EVO_EFFORTS,
    is_non_optimizable_in_thinking_mode as _non_optimizable,
)

EVOLVER_CAN_PROPOSE = True
EVOLVER_CAN_TEST = True
EVOLVER_CAN_PROMOTE = False
EVOLVER_CAN_CHANGE_GATES = False
EVOLVER_CAN_CHANGE_HOLDOUT = False

VALID_COMPONENTS = (
    "prompt",
    "tool_architecture",
    "context_selection",
    "editing_strategy",
    "stop_rule",
    "thinking_policy",
)

WEAKNESS_PATTERNS = (
    "repeated_identical_command",
    "same_file_repeatedly_reopened",
    "context_retrieval_misses",
    "unused_exposed_tools",
    "excessive_tool_loops",
    "premature_stop",
    "late_editing",
    "unnecessary_planning",
    "excessive_reasoning",
    "frequent_malformed_edits",
    "repeated_escalation_after_predictable_failure",
)

MIN_EVIDENCE_RUNS = 2


def _content_hash(text):
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


class Candidate:
    """Minimal candidate harness modification (order section 17)."""

    def __init__(
        self,
        hypothesis,
        observed_failure_pattern,
        affected_component,
        minimal_delta,
        expected_effect,
        risk,
        rollback_path,
        evaluation_plan,
    ):
        self.hypothesis = hypothesis
        self.observed_failure_pattern = observed_failure_pattern
        self.affected_component = affected_component
        self.minimal_delta = minimal_delta or {}
        self.expected_effect = expected_effect
        self.risk = risk
        self.rollback_path = rollback_path
        self.evaluation_plan = evaluation_plan

    def components_changed(self):
        return list(self.minimal_delta.keys())

    def material(self):
        """All textual candidate material subject to the leakage sentinel."""
        return " | ".join(
            [
                self.hypothesis,
                self.observed_failure_pattern,
                self.affected_component,
                str(self.minimal_delta),
                self.expected_effect,
            ]
        )


class EvolutionSandbox:
    """Propose/test-only sandbox. Cannot promote, cannot change gates/holdout."""

    def __init__(self, registry, holdout=None, train_set=None, validation_set=None):
        self.registry = registry
        self._holdout = list(holdout or [])
        self._train = list(train_set or [])
        self._validation = list(validation_set or [])
        # the holdout is immutable from the outside
        self._holdout_frozen = tuple(
            sorted(
                (t.get("id", ""), _content_hash(t.get("content", "")))
                for t in self._holdout
            )
        )

    @property
    def holdout(self):
        return list(self._holdout)

    @property
    def holdout_locked(self):
        return self._holdout_frozen

    def change_holdout(self, *args, **kwargs):
        return {
            "ok": False,
            "code": "HOLDOUT_LOCKED",
            "detail": "EVOLVER_CAN_CHANGE_HOLDOUT = NO",
        }

    # ------------------------------------------------------------ propose
    def propose(self, candidate, profile_patch=None, registry_entry=None):
        """Create a candidate harness entry (DRAFT/CANDIDATE). NEVER ACTIVE."""
        if not EVOLVER_CAN_PROPOSE:
            return {"ok": False, "code": "PROPOSE_DISABLED"}

        if not isinstance(candidate, Candidate):
            return {"ok": False, "code": "NOT_A_CANDIDATE"}

        # one component per experiment (order section 17)
        comps = candidate.components_changed()
        if len(comps) != 1 or comps[0] not in VALID_COMPONENTS:
            return {
                "ok": False,
                "code": "ONE_COMPONENT_RULE",
                "detail": "exactly one valid component per experiment, got %r"
                % (comps,),
            }

        # NON_OPTIMIZABLE guard (order section 5): thinking-mode-dead
        # parameters must never be treated as causal harness variables.
        for comp in comps:
            delta = (candidate.minimal_delta or {}).get(comp)
            if not isinstance(delta, dict):
                return {
                    "ok": False,
                    "code": "INVALID_MINIMAL_DELTA",
                    "detail": (
                        "minimal_delta[%r] must be a dict of {param: value}, "
                        "got %r" % (comp, type(delta).__name__)
                    ),
                }
            for key in delta:
                if _non_optimizable(key):
                    return {
                        "ok": False,
                        "code": "NON_OPTIMIZABLE_PARAMETER",
                        "detail": (
                            "%r is a documented no-op in thinking mode; "
                            "it is NON_OPTIMIZABLE and cannot be an "
                            "evolution dimension" % key
                        ),
                    }
            # reasoning_effort may only be optimized over (high, max);
            # case-insensitive, consistent with the adapter guard
            if "reasoning_effort" in delta:
                effort = str(delta["reasoning_effort"]).lower()
                if effort not in _EVO_EFFORTS:
                    return {
                        "ok": False,
                        "code": "NON_CANONICAL_REASONING_EFFORT",
                        "detail": (
                            "reasoning_effort %r is not a HAMH evolution "
                            "dimension; canonical optimization values "
                            "are %s"
                            % (delta["reasoning_effort"], ", ".join(_EVO_EFFORTS))
                        ),
                    }

        # leakage sentinel: candidate material must not reference holdout
        leak = self.leakage_check(candidate, profile_patch)
        if leak["leak"]:
            return {
                "ok": False,
                "code": "LEAKAGE_REJECTED",
                "detail": leak,
            }

        entry = registry_entry or {}
        entry = dict(entry)
        # proposals land as CANDIDATE — the sandbox controls the status,
        # never the caller (self-promotion denied at every surface)
        entry["status"] = "CANDIDATE"
        entry.setdefault("promotion_state", "OFFLINE_EVAL_PENDING")
        entry.setdefault("evaluation_reference", {})
        entry["evaluation_reference"]["candidate_material_hash"] = _content_hash(
            candidate.material()
        )
        return self.registry.add(entry)

    # ------------------------------------------------------------- leakage
    def leakage_check(self, candidate, profile_patch=None):
        """Leakage sentinel: any holdout content (id, content, content hash
        or distinctive content markers) appearing in candidate material ->
        LEAK. Holdout must never leak into prompts, context graphs or
        trajectory mining (order section 19)."""
        material = candidate.material()
        if profile_patch:
            material += " | " + str(profile_patch)
        matched = set()
        for hid, hhash in self._holdout_frozen:
            if hid and hid in material:
                matched.add(hid)
            if hhash and hhash in material:
                matched.add(hhash)
        # content markers: holdout content itself or its distinctive tokens
        # (alphanumeric runs >= 7 chars — unlikely to collide by chance).
        # Content may live under any string field of the holdout item.
        for t in self._holdout:
            content = " | ".join(str(v) for v in t.values() if isinstance(v, str) and v)
            if content and content in material:
                matched.add("content:" + t.get("id", "?"))
            for token in re.findall(r"[A-Za-z0-9_\-]{7,}", content):
                if token in material:
                    matched.add("token:" + token)
        return {
            "leak": bool(matched),
            "matched": sorted(matched),
        }

    # ------------------------------------------------------ matched compute
    @staticmethod
    def matched_compute_verdict(
        metrics_a, metrics_b, metrics_c, primary="verified_success_rate", epsilon=1e-9
    ):
        """A = current harness, B = candidate, C = current + equivalent extra
        inference/search budget (order section 20).

        Verdict IMPROVED only if B beats A AND the effect is not explained
        by C. Anything else: HARNESS_VALUE=NOT_PROVEN."""
        a = float(metrics_a.get(primary, 0.0))
        b = float(metrics_b.get(primary, 0.0))
        c = float(metrics_c.get(primary, 0.0))
        beats_a = b > a + epsilon
        explained_by_compute = c >= b - epsilon
        if beats_a and not explained_by_compute:
            return {
                "verdict": "IMPROVED",
                "primary": primary,
                "a": a,
                "b": b,
                "c": c,
                "beats_a": True,
                "explained_by_compute": False,
            }
        return {
            "verdict": "NOT_PROVEN",
            "primary": primary,
            "a": a,
            "b": b,
            "c": c,
            "beats_a": beats_a,
            "explained_by_compute": explained_by_compute,
        }


# ------------------------------------------------------------------------
def weakness_mining(trajectories, min_runs=MIN_EVIDENCE_RUNS):
    """Aggregate recurring failure patterns across trajectories.

    A single run is NOT sufficient evidence for a permanent harness change
    (order section 16). Returns patterns sorted by frequency (desc)."""
    counts = {}
    for t in trajectories or []:
        patterns = t.get("weakness_patterns") or []
        if isinstance(patterns, str):
            patterns = [patterns]
        for p in patterns:
            if p in WEAKNESS_PATTERNS:
                counts[p] = counts.get(p, 0) + 1
    return {
        "patterns": sorted(
            ((p, c) for p, c in counts.items() if c >= min_runs),
            key=lambda kv: (-kv[1], kv[0]),
        ),
        "total_runs": len(trajectories or []),
        "min_runs": min_runs,
    }
