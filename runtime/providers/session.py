#!/usr/bin/env python3
"""Run-scoped routing state backed by the canonical adapter ledger."""

import json
import os
import threading


class RunRoutingState:
    """Append routing events to the existing runs.jsonl source of truth."""

    def __init__(self, ledger_path=None):
        self.ledger_path = ledger_path
        self._lock = threading.RLock()

    @staticmethod
    def empty(run_id):
        return {
            "run_id": run_id,
            "run_model_exclusions": set(),
            "provider_exclusions": set(),
            "task_model_exclusions": {},
            "model_transport_failure_count": {},
            "model_semantic_failure_count": {},
            "model_last_failure_class": {},
            "model_selection_history": [],
            "distinct_task_failures": {},
        }

    def load(self, run_id):
        state = self.empty(run_id)
        if not self.ledger_path or not os.path.exists(self.ledger_path):
            return state
        try:
            with open(self.ledger_path, encoding="utf-8") as stream:
                for line in stream:
                    try:
                        event = json.loads(line)
                    except (TypeError, ValueError):
                        continue
                    if event.get("_event") != "routing_state" or event.get("run_id") != run_id:
                        continue
                    self._apply(state, event)
        except OSError:
            return state
        return state

    @staticmethod
    def _apply(state, event):
        for key in (
            "run_model_exclusions", "provider_exclusions",
        ):
            value = event.get(key)
            if value:
                state[key].update(value)
        for key in (
            "task_model_exclusions", "model_transport_failure_count",
            "model_semantic_failure_count", "model_last_failure_class",
            "distinct_task_failures",
        ):
            value = event.get(key)
            if isinstance(value, dict):
                if key == "task_model_exclusions":
                    for task, models in value.items():
                        state[key].setdefault(task, set()).update(models)
                elif key == "distinct_task_failures":
                    for model, tasks in value.items():
                        state[key].setdefault(model, set()).update(tasks)
                else:
                    state[key].update(value)
        if event.get("selection"):
            state["model_selection_history"].append(event["selection"])
            del state["model_selection_history"][:-200]

    def record(self, run_id, **event):
        if not self.ledger_path:
            return
        payload = {"_event": "routing_state", "run_id": run_id, **event}
        directory = os.path.dirname(self.ledger_path) or "."
        os.makedirs(directory, exist_ok=True)
        with self._lock, open(self.ledger_path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
