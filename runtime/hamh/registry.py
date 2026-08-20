#!/usr/bin/env python3
"""HAMH harness registry (ADR H4/H5) — JSON-file-backed, deterministic.

States: DRAFT, CANDIDATE, SHADOW, CANARY, ACTIVE, RETIRED, REJECTED.

Transition rules (deterministic, gate-bound):

    DRAFT     -> CANDIDATE   (valid contract + one-component minimal delta)
    CANDIDATE -> SHADOW      (OFFLINE EVAL + VALIDATION passed, no leakage)
    SHADOW    -> CANARY      (HOLDOUT passed, no regression break)
    CANARY    -> ACTIVE      (authorized promote() ONLY)
    *         -> RETIRED     (explicit retirement)
    *         -> REJECTED    (gate failure, regression, leakage, NOT_PROVEN)

ACTIVE can be reached ONLY through the authorized promotion path
(EVOLVER_CAN_PROMOTE=NO). The registry keeps a per-identity ACTIVE history so
rollback() restores the exact previous active configuration (AC-8).

Entries are deep-copied on read and write: profile mutation from one cell can
never leak into another cell (isolation tests A/B).
"""

import copy
import datetime as dt
import hmac
import json
import os
import threading

from contracts import registry as _contracts
from contracts.fingerprint import fingerprint as _fp

STATES = ("DRAFT", "CANDIDATE", "SHADOW", "CANARY", "ACTIVE", "RETIRED", "REJECTED")

TRANSITIONS = {
    "DRAFT": {"CANDIDATE", "REJECTED", "RETIRED"},
    "CANDIDATE": {"SHADOW", "REJECTED", "RETIRED"},
    "SHADOW": {"CANARY", "REJECTED", "RETIRED"},
    "CANARY": {"ACTIVE", "REJECTED", "RETIRED"},
    "ACTIVE": {"RETIRED"},
    "RETIRED": set(),
    "REJECTED": set(),
}

CONTRACT_ID = "hamh.harness.v1"


def _now():
    return dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def identity_key(provider, model, model_revision, task_class, runtime_mode):
    return "%s|%s|%s|%s|%s" % (
        provider,
        model,
        model_revision or "",
        task_class,
        runtime_mode,
    )


class HarnessRegistry:
    """Central harness registry. Authority-gated promotion, rollback-capable."""

    def __init__(self, path=None, authority_token=None):
        """path: JSON file backing the registry (test-safe tmp path).
        authority_token: promotion authority secret. If None, promote() is
        ALWAYS denied (secure default — no authority configured)."""
        self.path = path
        self._authority = authority_token
        self._entries = {}  # harness_id -> entry dict (validated)
        self._active_history = {}  # identity_key -> list of ACTIVE snapshots
        self._lock = threading.RLock()
        if path and os.path.exists(path):
            self._load()

    # ----------------------------------------------------------------- store
    def _load(self):
        try:
            with open(self.path) as f:
                data = json.load(f)
        except (ValueError, OSError):
            # corrupt registry file: back it up (never silently destroy)
            # and start empty — a broken registry must not crash dispatch
            backup = "%s.corrupt-%s" % (
                self.path,
                dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"),
            )
            try:
                os.replace(self.path, backup)
            except OSError:
                pass
            data = {}
        for hid, entry in (data.get("entries") or {}).items():
            self._entries[hid] = copy.deepcopy(entry)
        for key, snapshots in (data.get("active_history") or {}).items():
            self._active_history[key] = copy.deepcopy(snapshots)

    def save(self):
        if not self.path:
            return
        with self._lock:
            payload = {
                "entries": self._entries,
                "active_history": self._active_history,
                "saved_at": _now(),
            }
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(payload, f, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)

    # ------------------------------------------------------------ authority
    def _authorized(self, token):
        if self._authority is None:
            return False  # no authority configured -> deny
        return hmac.compare_digest(str(token or ""), str(self._authority))

    # ------------------------------------------------------------- entries
    def add(self, entry):
        """Add a registry entry. Initial status must be DRAFT or CANDIDATE.
        NEVER ACTIVE (self-promotion denied at the API surface)."""
        entry = copy.deepcopy(entry)
        v = _contracts.validate(entry, CONTRACT_ID)
        if not v["ok"]:
            return {
                "ok": False,
                "code": "CONTRACT_INVALID",
                "errors": v["errors"],
            }
        if entry.get("status") not in ("DRAFT", "CANDIDATE"):
            return {
                "ok": False,
                "code": "INITIAL_STATUS_FORBIDDEN",
                "detail": "new entries may only start as DRAFT or CANDIDATE",
            }
        hid = entry["harness_id"]
        with self._lock:
            if hid in self._entries:
                return {"ok": False, "code": "DUPLICATE_HARNESS_ID"}
            self._entries[hid] = copy.deepcopy(entry)
            self.save()
        return {"ok": True, "harness_id": hid}

    def get(self, harness_id):
        """Deep copy on read: callers can never mutate the stored entry."""
        with self._lock:
            return copy.deepcopy(self._entries.get(harness_id))

    def entries(self):
        with self._lock:
            return copy.deepcopy(self._entries)

    def active_entries(self):
        with self._lock:
            return [
                copy.deepcopy(e)
                for e in self._entries.values()
                if e.get("status") == "ACTIVE"
            ]

    # ---------------------------------------------------------- transitions
    def transition(self, harness_id, new_state, reason=None, authority_token=None):
        """Deterministic state transition. CANARY->ACTIVE requires the
        authority token (promote gate)."""
        with self._lock:
            return self._transition_locked(
                harness_id, new_state, reason, authority_token
            )

    def _transition_locked(self, harness_id, new_state, reason, authority_token):
        entry = self._entries.get(harness_id)
        if entry is None:
            return {"ok": False, "code": "NOT_FOUND"}
        if new_state not in STATES:
            return {"ok": False, "code": "BAD_STATE"}
        cur = entry.get("status")
        if new_state == "ACTIVE" and cur != "CANARY":
            return {
                "ok": False,
                "code": "PROMOTE_FROM_CANARY_ONLY",
                "detail": "ACTIVE only via CANARY (authorized path)",
            }
        if new_state == "ACTIVE" and not self._authorized(authority_token):
            return {"ok": False, "code": "PROMOTE_DENIED"}
        if new_state not in TRANSITIONS.get(cur, set()):
            return {
                "ok": False,
                "code": "TRANSITION_FORBIDDEN",
                "detail": "%s -> %s not allowed" % (cur, new_state),
            }
        if new_state == "ACTIVE":
            self._activate(harness_id, reason)
        else:
            entry["status"] = new_state
            entry["promotion_state"] = reason or ("TRANSITION_" + new_state)
        self.save()
        return {"ok": True, "harness_id": harness_id, "status": new_state}

    def _activate(self, harness_id, reason):
        entry = self._entries[harness_id]
        key = identity_key(
            entry["provider"],
            entry["model"],
            entry.get("model_revision"),
            entry["task_class"],
            entry["runtime_mode"],
        )
        # deactivate current ACTIVE for this identity (push onto history)
        for other in list(self._entries.values()):
            if (
                other.get("status") == "ACTIVE"
                and other["harness_id"] != harness_id
                and identity_key(
                    other["provider"],
                    other["model"],
                    other.get("model_revision"),
                    other["task_class"],
                    other["runtime_mode"],
                )
                == key
            ):
                other["status"] = "RETIRED"
                other["promotion_state"] = "SUPERSEDED_BY_" + harness_id
                self._active_history.setdefault(key, []).append(copy.deepcopy(other))
        entry["status"] = "ACTIVE"
        entry["promotion_state"] = reason or "AUTHORIZED_PROMOTION"

    def promote(self, harness_id, authority_token):
        """Authorized promotion: CANARY -> ACTIVE. Denied without authority."""
        with self._lock:
            entry = self._entries.get(harness_id)
            if entry is None:
                return {"ok": False, "code": "NOT_FOUND"}
            if entry.get("status") != "CANARY":
                return {"ok": False, "code": "PROMOTE_FROM_CANARY_ONLY"}
            if not self._authorized(authority_token):
                return {"ok": False, "code": "PROMOTE_DENIED"}
            return self._transition_locked(
                harness_id, "ACTIVE", "AUTHORIZED_PROMOTION", authority_token
            )

    def rollback(self, harness_id, authority_token=None):
        """Restore EXACTLY the previous ACTIVE configuration for the identity
        of harness_id (AC-8). Requires authority (rollback is a
        promotion-class operation)."""
        with self._lock:
            entry = self._entries.get(harness_id)
            if entry is None:
                return {"ok": False, "code": "NOT_FOUND"}
            if not self._authorized(authority_token):
                return {"ok": False, "code": "ROLLBACK_DENIED"}
            key = identity_key(
                entry["provider"],
                entry["model"],
                entry.get("model_revision"),
                entry["task_class"],
                entry["runtime_mode"],
            )
            history = self._active_history.get(key) or []
            if not history:
                return {"ok": False, "code": "NO_PREVIOUS_ACTIVE"}
            previous = history.pop()
            # retire the current holder
            for other in list(self._entries.values()):
                if (
                    other.get("status") == "ACTIVE"
                    and identity_key(
                        other["provider"],
                        other["model"],
                        other.get("model_revision"),
                        other["task_class"],
                        other["runtime_mode"],
                    )
                    == key
                ):
                    other["status"] = "RETIRED"
                    other["promotion_state"] = "ROLLED_BACK"
            restored = copy.deepcopy(previous)
            restored["status"] = "ACTIVE"
            restored["promotion_state"] = "RESTORED_BY_ROLLBACK"
            # exact-config restore: reuse the SAME harness_id entry content
            self._entries[restored["harness_id"]] = restored
            self.save()
            return {"ok": True, "restored_harness_id": restored["harness_id"]}
