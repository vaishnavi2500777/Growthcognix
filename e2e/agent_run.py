"""Live agent check (uses the real AI provider): onboard a business, run the Market Research
Agent from the UI, wait for it to finish, and capture the report.
python3 e2e/agent_run.py [outdir]   env: E2E_COMPANY, E2E_WEBSITE"""
import os
import sys
import uuid

from playwright.sync_api import expect, sync_playwright

BASE = "http://localhost:3000"
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp"
COMPANY = os.environ.get("E2E_COMPANY", "Kamdhenu Limited")
WEBSITE = os.environ.get("E2E_WEBSITE", "https://www.kamdhenulimited.com")

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1366, "height": 900})
    pg = ctx.new_page()
    pg.goto(f"{BASE}/signup")
    pg.fill("input[name=full_name]", "Devi Singh")
    pg.fill("input[name=organization_name]", COMPANY)
    pg.fill("input[name=email]", f"agent-{uuid.uuid4().hex[:6]}@example.com")
    pg.fill("input[name=password]", "a-strong-password-1")
    pg.get_by_role("button", name="Create account").click()
    expect(pg).to_have_url(f"{BASE}/onboarding")
    pg.fill("input[name=website]", WEBSITE)
    pg.locator("form select").nth(0).select_option(label="Manufacturing")
    pg.locator("select[name=industry_id]").select_option(label="Steel and metals")
    pg.get_by_role("button", name="Both").click()
    pg.fill("textarea[name=description]",
            "We make TMT bars and building materials sold through dealers across India.")
    pg.fill("textarea[name=target_customers]", "Home builders, contractors and dealers")
    pg.get_by_label("Name", exact=True).first.fill("TMT bars")
    pg.fill("input[name=locations]", "Karnataka, India")
    pg.fill("input[name=languages]", "English, Kannada, Hindi")
    pg.get_by_role("button", name="Save and continue").click()
    expect(pg).to_have_url(f"{BASE}/dashboard")
    pg.goto(f"{BASE}/agents")
    pg.get_by_role("button", name="Run research").click()
    pg.wait_for_url(f"{BASE}/runs/**")
    pg.screenshot(path=f"{OUT}/10-run-working.png")
    expect(pg.get_by_text("Finished").or_(pg.get_by_text("Failed")).first).to_be_visible(timeout=120_000)
    pg.wait_for_timeout(500)
    pg.screenshot(path=f"{OUT}/11-run-report-light.png", full_page=True)
    pg.evaluate("document.documentElement.dataset.theme='dark'")
    pg.screenshot(path=f"{OUT}/12-run-report-dark.png", full_page=True)
    pg.goto(f"{BASE}/approvals")
    pg.screenshot(path=f"{OUT}/13-approvals-dark.png")
    pg.goto(f"{BASE}/dashboard")
    pg.screenshot(path=f"{OUT}/14-dashboard.png", full_page=True)
    print("AGENT RUN:", pg.url)
    b.close()
