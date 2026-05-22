from pathlib import Path
from playwright.sync_api import sync_playwright
from bb.security.session import SessionManager
import bb.config as cfg

sm = SessionManager(cfg.BB_DIR / "session.enc")
state = sm.decrypt_session()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(storage_state=state)
    page = ctx.new_page()

    url = "https://learn.senecapolytechnic.ca/ultra/course"
    print(f"Navigating to: {url}")
    page.goto(url, wait_until="load", timeout=30_000)
    page.wait_for_timeout(5000)
    print(f"Final URL: {page.url}")

    for sel in [
        "article[data-course-id]",
        "[data-course-id]",
        "a[href*='/ultra/courses/']",
        "[analytics-id*='course']",
        ".multi-column-course-id",
        "[id^='course-name-']",
        "[id^='course-id-']",
    ]:
        els = page.query_selector_all(sel)
        if els:
            print(f"  FOUND {len(els)}x '{sel}'")
            for el in els[:5]:
                print(f"    text={el.inner_text()[:80].strip()!r}")
        else:
            print(f"  none  '{sel}'")

    html = page.content()
    Path("/tmp/courses_page.html").write_text(html, encoding="utf-8")
    print(f"\nHTML saved ({len(html)} bytes)")
    browser.close()
