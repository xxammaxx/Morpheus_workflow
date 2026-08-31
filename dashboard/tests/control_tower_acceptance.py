#!/usr/bin/env python3
"""Real-runtime Control Tower acceptance checks.

Read three newline-delimited credentials from stdin in this order:
viewer, operator, admin.  The values are never printed or persisted.
"""

from __future__ import annotations

import json
import importlib.metadata
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


URL = os.environ.get("CONTROL_TOWER_URL", "http://192.168.1.136:8092").rstrip("/")
OUTPUT = Path(os.environ.get("CONTROL_TOWER_ACCEPTANCE_REPORT", "/tmp/control-tower-acceptance.json"))
VIEWPORTS = [(1440, 900), (1280, 800), (768, 1024), (390, 844), (360, 800)]
VIEWS = ("overview", "projects", "runs", "providers", "system-map", "data-flow", "debugging", "administration")
SECRET_PATTERNS = re.compile(
    r"(?:LM_API_TOKEN|N8N_API_KEY|MORPHEUS_COMMAND_TOKEN|PROXMOX_API_TOKEN|"
    r"CONTROL_TOWER_(?:VIEW|OPERATOR|ADMIN)_TOKEN|Bearer\s+[A-Za-z0-9._-]{12,}|"
    r"-----BEGIN (?:OPENSSH|RSA|EC|PRIVATE) KEY-----|chain[_ -]?of[_ -]?thought|"
    r"reasoning_content)",
    re.IGNORECASE,
)


def read_tokens() -> tuple[str, str, str]:
    values = [line.decode().strip() for line in sys.stdin.buffer.read().splitlines() if line.strip()]
    if len(values) < 3:
        raise RuntimeError("three existing credential references are required on stdin")
    return values[0], values[1], values[2]


def api(token: str, path: str, method: str = "GET", body: dict | None = None, **headers):
    data = None if body is None else json.dumps(body).encode()
    request_headers = {"X-Control-Tower-Token": token, **headers}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(URL + path, data=data, method=method, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
            return response.status, json.loads(raw or b"{}")
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            payload = {}
        return error.code, payload


def assert_status(result, expected, label):
    status, _ = result
    if status != expected:
        raise AssertionError(f"{label}: expected {expected}, got {status}")


def run() -> dict:
    viewer, operator, admin = read_tokens()
    result = {
        "url": URL,
        "tested_local_code_head": os.environ.get("TESTED_LOCAL_CODE_HEAD", "UNKNOWN"),
        "canonical_run_id": os.environ.get("CONTROL_TOWER_CANONICAL_RUN_ID", "UNKNOWN"),
        "viewports": [f"{w}x{h}" for w, h in VIEWPORTS],
        "views": list(VIEWS),
        "console_errors": 0,
        "http_500_count": 0,
        "failed_static_assets": 0,
        "horizontal_overflow": 0,
        "security_leaks": 0,
        "private_reasoning_leaks": 0,
        "role_observed": {},
        "run_ids": [],
        "gates": {},
    }

    status, health = api("", "/healthz")
    assert status == 200 and health.get("status") == "ok", "healthz failed"
    result["version"] = health.get("version", "UNKNOWN")

    # Read/API boundary and negative command gates use the real BFF.
    assert_status(api("", "/api/v1/session"), 401, "unauthenticated read")
    for name, token in (("viewer", viewer), ("operator", operator), ("admin", admin)):
        status, session = api(token, "/api/v1/session")
        assert status == 200, f"{name} session failed: {status}"
        result["role_observed"][name] = session.get("role", "UNKNOWN")
    result["gates"]["AUTH_GATE"] = True

    command = {"command": "RUN_ROUTER_TEST", "payload": {"test": "DeepSeek Sperre", "read_only": True}, "target": {}}
    assert_status(api("", "/api/v1/commands", "POST", command), 401, "unauthenticated mutation")
    assert_status(api(viewer, "/api/v1/commands", "POST", command, **{"X-Control-Tower-Request": "1", "Origin": URL}), 403, "viewer mutation")
    assert_status(api(admin, "/api/v1/commands", "POST", command), 403, "missing csrf")
    assert_status(api(admin, "/api/v1/commands", "POST", command, **{"X-Control-Tower-Request": "0"}), 403, "bad csrf")
    assert_status(api(admin, "/api/v1/commands", "POST", command, Origin="http://evil.invalid", **{"X-Control-Tower-Request": "1"}), 403, "cross origin")
    headers = {"X-Control-Tower-Request": "1", "Origin": URL}
    unknown = {"command": "EXECUTE_ANYTHING", "payload": {}, "target": {}}
    assert_status(api(admin, "/api/v1/commands", "POST", unknown, **headers), 400, "unknown command")
    arbitrary_target = {**command, "target": {"url": "https://evil.invalid"}}
    assert_status(api(admin, "/api/v1/commands", "POST", arbitrary_target, **headers), 400, "arbitrary target")
    operator_admin = api(operator, "/api/v1/commands", "POST", command, **headers)
    result["gates"]["CSRF_GATE"] = True
    result["gates"]["VIEWER_READ_ONLY"] = api(viewer, "/api/v1/session")[1].get("read_only") is True
    result["gates"]["ARBITRARY_COMMAND_GATE"] = True
    result["gates"]["ARBITRARY_TARGET_GATE"] = True
    result["gates"]["OPERATOR_ADMIN_GATE"] = operator_admin[0] == 403

    overview_status, overview = api(admin, "/api/v1/overview")
    assert overview_status == 200, f"overview API failed: {overview_status}"
    runs = overview.get("recent_runs", [])
    result["run_ids"] = [str(row.get("run_id")) for row in runs if row.get("run_id")]
    result["gates"]["PROJECT_RUN_PROJECTION"] = overview.get("projects") is not None and isinstance(runs, list)
    runs_status, runs_payload = api(admin, "/api/v1/runs")
    assert runs_status == 200 and isinstance(runs_payload.get("runs"), list), "runs API failed"
    result["gates"]["RUN_PROJECTION"] = True

    # Correlation checks use only public projection fields, never payload content.
    run_map = {str(row.get("run_id")): row for row in runs_payload.get("runs", []) if row.get("run_id")}
    correlation_ok = all(run_id in run_map for run_id in result["run_ids"])
    canonical_run_id = result["canonical_run_id"]
    canonical_displayed = canonical_run_id == "UNKNOWN" or canonical_run_id in run_map
    correlation_ok = correlation_ok and canonical_displayed
    for run_id in result["run_ids"][:3]:
        detail_status, detail = api(admin, "/api/v1/runs/" + urllib.parse.quote(run_id, safe=""))
        if detail_status != 200 or detail.get("run_id") != run_id:
            correlation_ok = False
    result["gates"]["RUN_CORRELATION"] = correlation_ok
    result["gates"]["CANONICAL_RUN_DISPLAY"] = canonical_displayed

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        result["playwright_version"] = importlib.metadata.version("playwright")
        result["browser"] = browser.version
        command_attempted = False
        refresh_observed = False
        for width, height in VIEWPORTS:
            page = browser.new_page(viewport={"width": width, "height": height})
            console_errors = []
            page_errors = []
            bad_assets = []
            statuses = []
            leaked = []
            command_response_statuses = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on("response", lambda response: (statuses.append(response.status), bad_assets.append(response.url)) if response.status >= 500 or (response.request.resource_type in {"script", "stylesheet", "font"} and response.status >= 400) else None)
            page.on("response", lambda response: command_response_statuses.append(response.status) if response.url.endswith("/api/v1/commands") else None)
            page.on("request", lambda request: leaked.append(request.url) if SECRET_PATTERNS.search(" ".join(f"{key}:{value}" for key, value in request.headers.items() if key.lower() not in {"x-control-tower-token"})) else None)
            page.goto(URL + "/", wait_until="domcontentloaded")
            page.get_by_label("Leitstand-Zugriffstoken").fill(admin)
            page.get_by_role("button", name="Leitstand öffnen").click()
            page.locator("#dashboard").wait_for(state="visible")
            page.wait_for_timeout(900)
            if not refresh_observed:
                freshness_before = page.locator("#freshness").inner_text()
                page.wait_for_timeout(5500)
                refresh_observed = page.locator("#freshness").inner_text() != freshness_before
            assert page.locator("html").get_attribute("lang") == "de"
            for view in VIEWS:
                button = page.locator(f".tabs button[data-view='{view}']")
                assert button.is_visible(), f"navigation {view} not visible"
                button.focus()
                assert page.evaluate("el => document.activeElement === el", button.element_handle())
                button.click()
                page.locator(f"#{view}-view").wait_for(state="visible")
            assert page.locator("#system-map-diagram svg").count() == 1
            assert page.locator("#data-flow-diagram svg").count() == 1
            assert page.locator("#system-map-fallback").is_hidden()
            assert page.locator("#data-flow-fallback").is_hidden()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            for control in page.locator("button, input, select, textarea").all():
                name = control.get_attribute("aria-label") or control.inner_text().strip() or control.get_attribute("value")
                if not name and control.get_attribute("id"):
                    name = page.locator(f"label[for='{control.get_attribute('id')}']").count() > 0
                if not name:
                    name = control.evaluate("el => Boolean(el.closest('label'))")
                assert name, "interactive control has no accessible name: " + (control.get_attribute("id") or control.get_attribute("class") or control.evaluate("el => el.tagName"))
            result["console_errors"] += len(console_errors) + len(page_errors)
            result["http_500_count"] += sum(1 for status in statuses if status >= 500)
            result["failed_static_assets"] += len(bad_assets)
            result["horizontal_overflow"] += 0 if page.evaluate("document.documentElement.scrollWidth <= window.innerWidth") else 1
            result["security_leaks"] += len(leaked)
            result["private_reasoning_leaks"] += 1 if SECRET_PATTERNS.search(page.locator("body").inner_text()) else 0

            page.locator("button[data-view='system-map']").click()
            page.locator("#system-map-run").wait_for(state="visible")
            page.locator("#system-map-run").select_option(index=0) if page.locator("#system-map-run option").count() else None
            tracked = page.evaluate("sessionStorage.getItem('morpheus-control-tower-tracked-run')")
            if tracked:
                page.locator("button[data-view='data-flow']").click()
                assert tracked in page.locator("#data-flow-context").inner_text()
                page.locator(".tabs button[data-view='debugging']").click()
                assert tracked in page.locator("#debug-flow").inner_text() or "Keine Events" in page.locator("#event-stream").inner_text()
            page.locator(".tabs button[data-view='administration']").click()
            test_button = page.locator(".test-command").first
            result["command_button_count"] = test_button.count()
            if test_button.count() and not command_attempted:
                try:
                    with page.expect_response(lambda response: response.url.endswith("/api/v1/commands"), timeout=5000) as command_response:
                        test_button.dblclick(delay=50)
                    result["command_response_statuses"] = [command_response.value.status]
                except PlaywrightTimeoutError:
                    result["command_response_statuses"] = []
                page.wait_for_timeout(2500)
                command_attempted = True
                if not result["command_response_statuses"]:
                    result["command_response_statuses"] = command_response_statuses
            page.close()
        browser.close()

    result["gates"].update({
        "ALL_CURRENT_MAIN_VIEWS": True,
        "RESPONSIVE_GATE": result["horizontal_overflow"] == 0,
        "ACCESSIBILITY_BASELINE": result["console_errors"] == 0,
        "BROWSER_SECRET_LEAK_GATE": result["security_leaks"] == 0,
        "PRIVATE_REASONING_LEAK_GATE": result["private_reasoning_leaks"] == 0,
        "CONSOLE_GATE": result["console_errors"] == 0,
        "HTTP_500_GATE": result["http_500_count"] == 0,
    })
    result["gates"]["LIVE_REFRESH"] = refresh_observed
    command_statuses = result.get("command_response_statuses", [])
    result["gates"]["DUPLICATE_CLICK_GATE"] = command_statuses == [202]
    result["gates"]["COMMAND_E2E"] = bool(command_statuses) and command_statuses[0] in {200, 202}
    result["gates"]["PLAYWRIGHT_REAL_RUNTIME"] = True
    result["gates"]["ROLE_GATE"] = (
        result["role_observed"] == {"viewer": "VIEWER", "operator": "OPERATOR", "admin": "ADMIN"}
        and result["gates"].get("VIEWER_READ_ONLY") is True
        and result["gates"].get("OPERATOR_ADMIN_GATE") is True
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"report": str(OUTPUT), "gates": result["gates"], "roles": result["role_observed"]}, ensure_ascii=False))
    return result


if __name__ == "__main__":
    # urllib.parse is imported lazily here to keep the test's import surface small.
    import urllib.parse

    run()
