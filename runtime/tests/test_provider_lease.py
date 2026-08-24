#!/usr/bin/env python3
"""Provider probe lease acceptance tests (no external provider calls)."""

import json
import os
import tempfile
import time

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from providers.lease import ProbeLeaseError, ProviderProbeLease


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    print("PASS " + name)


def main():
    with tempfile.TemporaryDirectory() as state:
        path = os.path.join(state, "lease.json")
        now = [1000.0]
        lease = ProviderProbeLease(path=path, ttl=120, clock=lambda: now[0])
        lease.check_ordinary("openrouter")
        check("T1_NORMAL_TRAFFIC_ALLOWED_WITHOUT_LEASE", True)
        lease_a = lease.acquire("openrouter", "test-owner")
        try:
            lease.check_ordinary("openrouter")
        except ProbeLeaseError as exc:
            check("T2_LEASE_BLOCKS_ORDINARY_TRAFFIC", str(exc) == "PROVIDER_PROBE_LEASE_ACTIVE")
        authorized = lease.authorize("openrouter", lease_a["lease_id"])
        check("T3_CORRECT_LEASE_PERMITS_ONE_PROBE", authorized["remaining_probe_requests"] == 0)
        try:
            lease.authorize("openrouter", lease_a["lease_id"])
        except ProbeLeaseError as exc:
            check("T4_SECOND_PROBE_DENIED", str(exc) == "PROVIDER_PROBE_LEASE_EXHAUSTED")
        lease.release(lease_a["lease_id"])
        lease_b = lease.acquire("openrouter", "test-owner")
        try:
            lease.authorize("openrouter", "wrong")
        except ProbeLeaseError as exc:
            check("T5_WRONG_LEASE_ID_DENIED", str(exc) == "PROVIDER_PROBE_LEASE_ID_INVALID")
        now[0] += 121
        lease.check_ordinary("openrouter")
        check("T6_TTL_EXPIRATION_RESTORES_ROUTING", True)
        # A new process sees the persisted active lease and remains fail-closed.
        lease_c = lease.acquire("openrouter", "test-owner")
        check("T7_RESTART_ACTIVE_LEASE_FAIL_SAFE", lease_c["lease_id"] != lease_b["lease_id"])
        try:
            lease.acquire("deepseek", "test-owner")
        except ProbeLeaseError as exc:
            check("T8_DEEPSEEK_NEVER_LEASE_ELIGIBLE", str(exc) == "PROVIDER_NOT_PROBE_ELIGIBLE")
        try:
            lease.acquire("paid-provider", "test-owner")
        except ProbeLeaseError as exc:
            check("T9_PAID_PROVIDER_NEVER_LEASE_ELIGIBLE", str(exc) == "PROVIDER_NOT_PROBE_ELIGIBLE")
        check("T10_LEASE_IS_NOT_SEMANTIC_RETRY", lease_c["remaining_probe_requests"] == 1)
    print("PROVIDER_PROBE_LEASE acceptance tests passed")


if __name__ == "__main__":
    main()
