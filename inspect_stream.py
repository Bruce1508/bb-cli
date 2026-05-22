"""Diagnostic: inspect the actual HTML of the activity stream and grades pages."""
import sys
import time

sys.path.insert(0, ".")

import bb.config as _config_module
from bb.config import load_config
from bb.security.session import SessionManager

cfg = load_config()
sm = SessionManager(_config_module.BB_DIR / "session.enc")
state = sm.decrypt_session()

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=state)

    # ── Activity Stream ──────────────────────────────────────────────
    print("=" * 60)
    print("ACTIVITY STREAM PAGE")
    print("=" * 60)
    page = context.new_page()
    page.goto(f"{cfg.lms_url}/ultra/stream", wait_until="load", timeout=30_000)
    print(f"Landed on: {page.url}")

    # Wait up to 30s for any stream item to appear
    try:
        page.wait_for_selector("li", timeout=30_000)
    except Exception:
        pass

    time.sleep(5)  # extra buffer for slow Angular renders

    # Try every plausible stream item selector
    for sel in [
        "li.stream-item-container",
        ".stream-item-container",
        "li[class*='stream']",
        ".activity-feed li",
        "li",
        "[analytics-id*='stream.entry']",
    ]:
        els = page.query_selector_all(sel)
        print(f"  {sel!r:45s} → {len(els)} elements")

    # Print first 2000 chars of activity-feed inner HTML
    feed = page.query_selector(".activity-feed")
    if feed:
        inner = feed.inner_html()
        print(f"\nactivity-feed inner HTML ({len(inner)} chars):")
        print(inner[:2000])
    else:
        print("\nNo .activity-feed found — dumping first 3000 chars of body:")
        body = page.query_selector("body")
        print(body.inner_html()[:3000] if body else "(no body)")

    # Save full HTML
    stream_html = page.content()
    open("/tmp/bb_stream_debug.html", "w").write(stream_html)
    print(f"\nFull HTML saved to /tmp/bb_stream_debug.html ({len(stream_html)} bytes)")
    page.close()

    # ── Grades Page ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("GRADES PAGE")
    print("=" * 60)
    page2 = context.new_page()
    page2.goto(f"{cfg.lms_url}/ultra/grades", wait_until="load", timeout=30_000)
    print(f"Landed on: {page2.url}")
    time.sleep(10)

    for sel in [
        "[data-testid='grade-row']",
        ".graded-item-row",
        "tr",
        "[class*='grade']",
        "[class*='Grade']",
    ]:
        els = page2.query_selector_all(sel)
        print(f"  {sel!r:45s} → {len(els)} elements")

    grades_html = page2.content()
    open("/tmp/bb_grades_debug.html", "w").write(grades_html)
    print(f"\nFull HTML saved to /tmp/bb_grades_debug.html ({len(grades_html)} bytes)")
    page2.close()

    browser.close()

print("\nDone.")
