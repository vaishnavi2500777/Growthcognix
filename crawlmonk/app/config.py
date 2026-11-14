import os
DATABASE_URL = os.getenv("DATABASE_URL", "")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-secret-change-me")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
BROWSER_ENABLED = os.getenv("BROWSER_ENABLED", "1") == "1"
BOT_UA = "CrawlMonkBot/1.0 (+https://crawlmonk.onrender.com; contact +91 9019088160)"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
MOBILE_UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/131.0 Mobile Safari/537.36")
DAILY_CREDITS = int(os.getenv("DAILY_CREDITS", "3000"))
MAX_CRAWL_LIMIT = int(os.getenv("MAX_CRAWL_LIMIT", "200"))
PUBLIC_URL = os.getenv("PUBLIC_URL", "https://crawlmonk.onrender.com")
