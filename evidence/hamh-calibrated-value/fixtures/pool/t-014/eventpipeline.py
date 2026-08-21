"""Event pipeline (task fixture t-014)."""


def process_events(events, handle) -> dict:
    """Process events in seq order, idempotently, error-isolated.

    events: list of {"event_id": str, "seq": int, ...}
    handle: callable(event) -> None (ok) or raises/returns error
    Returns {"processed": int, "failed": [event_id, ...]}
    """
    processed_ids = set()
    failed = []
    processed = 0
    for event in sorted(events, key=lambda e: e["seq"]):
        if event["event_id"] in processed_ids:
            continue
        try:
            result = handle(event)
            if result is not None:
                failed.append(event["event_id"])
                continue
        except Exception:
            failed.append(event["event_id"])
            continue
        processed_ids.add(event["event_id"])
        processed += 1
    return {"processed": processed, "failed": failed}
