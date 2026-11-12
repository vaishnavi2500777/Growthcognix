"""End-to-end smoke test: sign up -> onboarding -> dashboard, light + dark, desktop + mobile.
Run with the API on :8000 and the web app on :3000.  python3 e2e/smoke.py [outdir]"""
import sys
import uuid

from playwright.sync_api import expect, sync_playwright

BASE = "http://localhost:3000"
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp"


def run():
    email = f"devi-{uuid.uuid4().hex[:6]}@example.com"
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1366, "height": 900})
        pg = ctx.new_page()
        pg.goto(f"{BASE}/dashboard")
        expect(pg).to_have_url(f"{BASE}/login")
        pg.screenshot(path=f"{OUT}/01-login-light.png")
        pg.get_by_role("link", name="Create an account").click()
        pg.fill("input[name=full_name]", "Devi Singh")
        pg.fill("input[name=organization_name]", "Sri Lakshmi Steels")
        pg.fill("input[name=email]", email)
        pg.fill("input[name=password]", "short")
        pg.get_by_role("button", name="Create account").click()
        pg.wait_for_timeout(300)
        assert pg.url.endswith("/signup")  # browser minLength blocks short password
        pg.fill("input[name=password]", "a-strong-password-1")
        pg.get_by_role("button", name="Create account").click()
        expect(pg).to_have_url(f"{BASE}/onboarding")
        pg.fill("input[name=company_name]", "Sri Lakshmi Steels")
        pg.fill("input[name=website]", "srilakshmisteels.in")
        pg.locator("form select").nth(0).select_option(label="Manufacturing")
        pg.locator("select[name=industry_id]").select_option(label="Steel and metals")
        pg.get_by_role("button", name="B2B").click()
        pg.fill("textarea[name=description]",
                "We make TMT bars and structural steel for builders across North Karnataka.")
        pg.fill("textarea[name=target_customers]", "Builders, contractors and hardware dealers")
        pg.get_by_label("Name", exact=True).first.fill("TMT bars")
        pg.get_by_role("button", name="+ Add another").click()
        pg.get_by_label("Type", exact=True).nth(1).select_option("service")
        pg.get_by_label("Name", exact=True).nth(1).fill("Cut and bend")
        pg.fill("input[name=locations]", "Vijayapura, Bagalkot, Hubballi")
        pg.fill("input[name=languages]", "Kannada, English")
        pg.screenshot(path=f"{OUT}/02-onboarding-light.png", full_page=True)
        pg.get_by_role("button", name="Save and continue").click()
        expect(pg).to_have_url(f"{BASE}/dashboard")
        expect(pg.get_by_text("Sri Lakshmi Steels").first).to_be_visible()
        expect(pg.get_by_text("Manufacturing · Steel and metals · B2B")).to_be_visible()
        pg.screenshot(path=f"{OUT}/03-dashboard-light.png", full_page=True)
        pg.get_by_role("button", name="Switch light or dark theme").last.click()
        pg.screenshot(path=f"{OUT}/04-dashboard-dark.png", full_page=True)
        pg.goto(f"{BASE}/agents")
        pg.screenshot(path=f"{OUT}/05-agents-dark.png")
        pg.goto(f"{BASE}/business")
        assert pg.locator("select[name=industry_id] option:checked").inner_text() == "Steel and metals"
        # sign out, sign back in
        pg.goto(f"{BASE}/dashboard")
        pg.get_by_role("button", name="Sign out").click()
        expect(pg).to_have_url(f"{BASE}/login")
        pg.fill("input[name=email]", email)
        pg.fill("input[name=password]", "wrong-password")
        pg.get_by_role("button", name="Sign in").click()
        expect(pg.get_by_text("Email or password is incorrect.")).to_be_visible()
        expect(pg.locator("input[name=email]")).to_have_value(email)  # values kept on error
        pg.fill("input[name=password]", "a-strong-password-1")
        pg.get_by_role("button", name="Sign in").click()
        expect(pg).to_have_url(f"{BASE}/dashboard")
        m = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                          storage_state=ctx.storage_state())
        mp = m.new_page()
        mp.goto(f"{BASE}/dashboard")
        mp.screenshot(path=f"{OUT}/06-dashboard-mobile-dark.png", full_page=True)
        b.close()
    print("E2E OK", email)


if __name__ == "__main__":
    run()
