"""Deterministic adaptive-harness primitives.

This package is deliberately offline and control-plane agnostic: it records,
selects, scores and compares evidence. It never selects a paid route, writes
production state, or promotes a candidate.
"""

VERSION = "1.0.0"

__all__ = ["benchmark", "context", "experience", "evolution", "repo_explorer"]
