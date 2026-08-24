# Projektion und Betriebsmetriken

Active states include all canonical pipeline states. Terminal 24-hour counts
use UTC timestamps, prefer `ended_at` over `updated_at`, and ignore missing or
invalid timestamps. Recent runs sort by `updated_at`. Stale active runs use
the 1800-second default. Two eligible free providers are required for healthy.
