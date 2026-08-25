#!/usr/bin/env python3
"""Backward-compatible entry point for the dynamic OpenCode credential sync."""

from sync_opencode_credentials import main


if __name__ == "__main__":
    raise SystemExit(main())
