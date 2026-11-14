"""Live end-to-end smoke test against a deployed CrawlMonk. Usage: python live_smoke.py BASE [email] [password]"""
import json
import sys
import time

import httpx

BASE = sys.argv[1].rstrip("/")
EMAIL = sys.argv[2] if len(sys.argv) > 2 else "selftest@crawlmonk.local"
PW = sys.argv[3] if len(sys.argv) > 3 else "selftest-pass-123"
c = httpx.Client(timeout=180)


def tok():
    r = c.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PW})
    if r.status_code != 200:
        r = c.post(f"{BASE}/auth/signup", json={"email": EMAIL, "password": PW})
    return r.json()["token"]


H = {"Authorization": "Bearer " + tok()}


def post(p, b):
    r = c.post(BASE + p, json=b, headers=H)
    return r.status_code, r.json()


def wait(path, key="status", t=600):
    t0 = time.time()
    while time.time() - t0 < t:
        d = c.get(BASE + path, headers=H).json()
        st = d.get("jobStatus") or d.get("status")
        if st not in ("queued", "running", "scraping"):
            return d
        time.sleep(5)
    return d


if __name__ == "__main__":
    what = sys.argv[4] if len(sys.argv) > 4 else "all"
    print(c.get(BASE + "/health").json())
    if what in ("all", "scrape"):
        s, d = post("/v1/scrape", {"url": "https://www.python.org/about/", "formats": ["markdown", "links", "contacts"]})
        print("scrape", s, d["data"]["metadata"].get("title"), d["data"]["metadata"].get("engine"), len(d["data"]["markdown"]))
    print(json.dumps(post("/v1/scrape", {"url": "http://169.254.169.254/latest/meta-data"})[1]))
