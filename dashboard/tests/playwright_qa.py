import json
import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = os.environ.get("CONTROL_TOWER_URL", "http://192.168.1.136:8092")
TOKEN = os.environ.get("CONTROL_TOWER_TOKEN", "") or sys.stdin.read().strip()
OUT = Path(os.environ.get("CONTROL_TOWER_SCREENSHOTS", "screenshots"))
OUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for width, height, label in ((1440, 900, "desktop-1440x900"), (1280, 720, "desktop-1280x720"), (390, 844, "mobile-390x844"), (360, 800, "mobile-360x800")):
        page = browser.new_page(viewport={"width": width, "height": height})
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        responses = []
        page.on("response", lambda response: responses.append(response.status))
        page.set_default_timeout(10000)
        page.goto(URL + "/", wait_until="domcontentloaded")
        assert page.get_by_role("heading", name="Zugriff auf den Leitstand").is_visible()
        page.get_by_label("Leitstand-Zugriffstoken").fill(TOKEN)
        page.get_by_role("button", name="Leitstand öffnen").click()
        page.get_by_role("heading", name="LEITSTAND", exact=True).wait_for()
        page.wait_for_timeout(700)
        page.screenshot(path=str(OUT / (label + "-overview.png")), full_page=True)
        assert page.locator("body").evaluate("el => el.scrollWidth <= window.innerWidth")
        assert not console_errors
        assert 500 not in responses
        page.get_by_role("button", name="Läufe", exact=True).click()
        page.get_by_role("button", name="Übersicht", exact=True).click()
        page.get_by_role("button", name="Referenzlauf „Golden Journey“").click()
        page.screenshot(path=str(OUT / (label + "-golden-detail.png")), full_page=True)
        page.get_by_role("button", name="Übersicht", exact=True).click()
        page.get_by_role("button", name="Referenzlauf „Fehlerbehebung“").wait_for()
        page.get_by_role("button", name="Referenzlauf „Fehlerbehebung“").click()
        page.screenshot(path=str(OUT / (label + "-failure-detail.png")), full_page=True)
        page.get_by_role("button", name="Übersicht", exact=True).click()
        page.get_by_role("button", name="Anbieter", exact=True).click()
        page.screenshot(path=str(OUT / (label + "-providers.png")), full_page=True)
        page.close()
    browser.close()
print(json.dumps({"VISUAL_QA": "PASS", "VIEWPORTS": 4, "CONSOLE_ERRORS": 0, "HTTP_500": 0}))
