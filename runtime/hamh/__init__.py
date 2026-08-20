#!/usr/bin/env python3
"""HAMH — Hierarchical Adaptive Model Harness.

Thin, clearly bounded evolution and specialization layer on top of the
AutoDev Harness v2 control plane (ADR-2026-08-20, decisions H1..H16).

Canonical principle:

    LLMs ARE WORKERS. LLMs ARE NOT THE CONTROLLER. n8n = CONTROL PLANE.

Layer model:
    A Shared Kernel        -> existing n8n control plane + runtime/contracts
    B Model Adapter        -> deepseek_adapter.py (provider API semantics)
    C Model Profile        -> profiles.ModelProfile (versioned)
    D Task Profiles        -> profiles.TaskProfile (research/plan/build/review)
    E Execution+Evolution  -> resolver.py, registry.py, evolution.py,
                              telemetry.py, taxonomy.py

Invariants (never weakened by HAMH):
    CONTROLLER_AUTHORITY=UNCHANGED   ROUTING_AUTHORITY=UNCHANGED
    RETRY_ESCALATION_SEPARATION=UNCHANGED  MCP_SECURITY_BOUNDARY=UNCHANGED
    PRODUCTION_SENTINELS=REQUIRED    VERIFIER_AUTHORITY=UNCHANGED
    AUDITABILITY=REQUIRED            ROLLBACK=REQUIRED
    MODEL_SELF_PROMOTION=DENIED      MODEL_SELF_SECURITY_CHANGE=DENIED
    MODEL_SELF_ROUTING_CHANGE=DENIED
"""

__all__ = [
    "taxonomy",
    "profiles",
    "registry",
    "resolver",
    "evolution",
    "telemetry",
    "deepseek_adapter",
]

VERSION = "1.0.0"
