import os
from pathlib import Path

# Load .env if python-dotenv is available; degrade gracefully if not so the
# offline smoke test (`python main.py check`) runs without extra deps.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass


# --- Feishu (reused from douyin-scraper, our own code) ---
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_APP_TOKEN = os.getenv("FEISHU_APP_TOKEN", "")
FEISHU_TABLE_ID = os.getenv("FEISHU_TABLE_ID", "")
NOTE_TABLE_ID = os.getenv("NOTE_TABLE_ID", "")
USER_TABLE_ID = os.getenv("USER_TABLE_ID", "")
COMMENT_TABLE_ID = os.getenv("COMMENT_TABLE_ID", "")

# --- Xiaohongshu ---
# Full cookie string from a logged-in xiaohongshu.com session (key fields: a1,
# web_session). Inject via the agent custom_env in Multica, never via comments.
XHS_COOKIE = os.getenv("XHS_COOKIE", "")
XHS_KEYWORD = os.getenv("XHS_KEYWORD", "")

PROXY_URL = os.getenv("PROXY_URL", "")
HEADLESS = os.getenv("XHS_HEADLESS", "false").lower() in ("1", "true", "yes")
MAX_PAGES = int(os.getenv("MAX_PAGES", "10"))
# XHS risk-control is stricter than Douyin; default to a slower cadence.
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "3"))

XHS_BASE_URL = "https://www.xiaohongshu.com"
# The /api/sns/web/... endpoints are served from the edith host.
XHS_API_BASE = "https://edith.xiaohongshu.com"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.xiaohongshu.com/",
    "Origin": "https://www.xiaohongshu.com",
    "Accept": "application/json, text/plain, */*",
}

FEISHU_API_BASE = "https://open.feishu.cn/open-apis"

# --- Live barrage (直播弹幕) ---
LIVE_TABLE_ID = os.getenv("LIVE_TABLE_ID", "")
LIVE_OUTPUT_MODE = os.getenv("LIVE_OUTPUT_MODE", "console")  # console | feishu | json
LIVE_DEFAULT_DURATION = int(os.getenv("LIVE_DEFAULT_DURATION", "0"))  # 0 = indefinite
