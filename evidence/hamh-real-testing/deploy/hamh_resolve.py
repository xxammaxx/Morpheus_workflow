#!/usr/bin/env python3
"""HAMH Resolver CLI — deterministic harness resolution from the shell.

Usage:
    hamh_resolve.py --provider deepseek --model deepseek-v4-flash \
        --task-class build --runtime-mode thinking [--revision 0731] \
        [--registry /path/registry.json]

Prints the hamh.resolution.v1 payload as JSON. Exit code 0.
Stdlib only.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "runtime"))
sys.path.insert(0, os.path.join(HERE, "runtime", "hamh"))
sys.path.insert(0, os.path.join(HERE, "runtime", "contracts"))

from hamh.resolver import resolve  # noqa: E402
from hamh.registry import HarnessRegistry  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--task-class", default="baseline")
    ap.add_argument("--runtime-mode", default="auto")
    ap.add_argument("--revision", default=None)
    ap.add_argument("--registry", default=None)
    ap.add_argument(
        "--no-registry",
        action="store_true",
        help="resolve without registry (pure baseline fallback)",
    )
    args = ap.parse_args()

    reg = None
    if not args.no_registry:
        registry_path = args.registry or os.path.join(
            os.path.dirname(HERE), "state", "registry.json"
        )
        reg = HarnessRegistry(registry_path) if os.path.exists(registry_path) else None

    payload = resolve(
        provider=args.provider,
        model=args.model,
        task_class=args.task_class,
        runtime_mode=args.runtime_mode,
        model_revision=args.revision,
        registry=reg,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
