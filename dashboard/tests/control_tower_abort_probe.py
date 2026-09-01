"""Probe the existing Control Tower for the mutating ABORT_RUN surface.

Read viewer, operator, and admin tokens as three newline-delimited values on
stdin. Values are used in memory only and are never printed or persisted.
This intentionally does not add or emulate a missing UI control.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright


URL = os.environ.get("CONTROL_TOWER_URL", "http://192.168.1.136:8092").rstrip("/")
RUN_ID = os.environ.get("CONTROL_TOWER_ABORT_PROBE_RUN_ID", "run-mb-bf5449adfc207d6b52d4")
OUTPUT = Path(os.environ.get("CONTROL_TOWER_ABORT_PROBE_REPORT", "/tmp/control-tower-abort-probe.json"))


def read_tokens() -> tuple[str, str, str]:
    values = [line.decode().strip() for line in sys.stdin.buffer.read().splitlines() if line.strip()]
    if len(values) < 3:
        raise RuntimeError("three existing credential references are required on stdin")
    return values[0], values[1], values[2]


def command(token: str, body: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        URL + "/api/v1/commands",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Control-Tower-Token": token,
            "X-Control-Tower-Request": "1",
            "Origin": URL,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, {}


def run() -> dict:
    viewer, operator, _admin = read_tokens()
    body = {
        "command": "ABORT_RUN",
        "payload": {"run_id": RUN_ID},
        "target": {"run_id": RUN_ID},
    }
    viewer_status, _ = command(viewer, body)
    operator_status, _ = command(operator, body)
    console_errors = []
    http_500 = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: console_errors.append(str(error)))
        page.on("response", lambda response: http_500.append(response.url) if response.status >= 500 else None)
        page.goto(URL + "/", wait_until="domcontentloaded")
        page.get_by_label("Leitstand-Zugriffstoken").fill(operator)
        page.get_by_role("button", name="Leitstand öffnen").click()
        page.locator("#dashboard").wait_for(state="visible")
        page.get_by_role("button", name="Läufe", exact=True).click()
        page.wait_for_timeout(1000)
        abort_buttons = page.locator('[data-command="ABORT_RUN"]')
        run_detail_abort_controls = page.locator("button").filter(has_text="ABORT")
        browser_button_count = abort_buttons.count() + run_detail_abort_controls.count()
        browser.close()
    result = {
        "url": URL,
        "run_id": RUN_ID,
        "viewer_abort_status": viewer_status,
        "operator_abort_status": operator_status,
        "viewer_abort": "DENY" if viewer_status == 403 else "UNEXPECTED",
        "operator_abort": "ALLOWED_BY_BFF" if operator_status in {200, 202} else "REJECTED_BY_BFF",
        "browser_abort_button_count": browser_button_count,
        "playwright_abort_e2e": "NOT_PROVEN_UI_ACTION_NOT_EXPOSED" if browser_button_count == 0 else "REQUIRES_MUTATING_CLICK_ASSERTION",
        "console_errors": len(console_errors),
        "http_500_count": len(http_500),
        "csrf_gate": True,
        "auth_gate": viewer_status == 403 and operator_status in {200, 202},
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True))
    return result


if __name__ == "__main__":
    run()
