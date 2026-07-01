"""Playwright browser manager for Xiaohongshu.

Holds a logged-in browser context and exposes an in-page ``fetch`` so signed
requests inherit the page's runtime state. Cookies are loaded, in order of
preference, from ``cookies.json`` in the skill root (produced by the ``login``
command — same pattern as douyin-scraper) or from the ``XHS_COOKIE`` env var.

Playwright is imported lazily so the offline smoke test does not require the
browser to be installed.
"""
import asyncio
import json
from pathlib import Path
from typing import Optional

from config.settings import XHS_BASE_URL, XHS_COOKIE, PROXY_URL

# Skill-root cookies file (a Playwright cookie array), written by `main.py login`.
COOKIE_FILE = Path(__file__).resolve().parent.parent / "cookies.json"

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
window.chrome = {runtime: {}};
Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
"""


def _cookie_string_to_list(cookie_str: str, domain: str = ".xiaohongshu.com") -> list:
    cookies = []
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            name, value = item.split("=", 1)
            cookies.append(
                {"name": name.strip(), "value": value.strip(), "domain": domain, "path": "/"}
            )
    return cookies


class XhsBrowser:
    def __init__(self, cookie: str = ""):
        self._cookie = cookie or XHS_COOKIE
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    async def start(self, headless: bool = True):
        from playwright.async_api import async_playwright  # lazy

        self._playwright = await async_playwright().start()
        launch_args = {
            "headless": headless,
            "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-gpu"],
        }
        if PROXY_URL:
            launch_args["proxy"] = {"server": PROXY_URL}
        self._browser = await self._playwright.chromium.launch(**launch_args)
        self._context = await self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        await self._context.add_init_script(STEALTH_JS)

        # Cookie source preference:
        #   1) cookies.json  — Playwright cookie array (written by `login`)
        #   2) xhs-cookies.json — {"XHS_COOKIE": "<cookie string>"}
        #   3) XHS_COOKIE env string
        loaded = False
        if COOKIE_FILE.exists():
            try:
                with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                    await self._context.add_cookies(json.load(f))
                loaded = True
            except Exception as e:
                print(f"[Browser] Failed to load cookies.json: {e}")
        if not loaded:
            alt = COOKIE_FILE.parent / "xhs-cookies.json"
            if alt.exists():
                try:
                    s = json.load(open(alt, encoding="utf-8")).get("XHS_COOKIE", "")
                    if s:
                        await self._context.add_cookies(_cookie_string_to_list(s))
                        loaded = True
                except Exception as e:
                    print(f"[Browser] Failed to load xhs-cookies.json: {e}")
        if not loaded and self._cookie:
            await self._context.add_cookies(_cookie_string_to_list(self._cookie))

        self._page = await self._context.new_page()

    @property
    def context(self):
        return self._context

    async def navigate(self, url: str):
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass
        await asyncio.sleep(2)

    async def save_cookies(self):
        cookies = await self._context.cookies()
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)

    async def cookie_dict(self) -> dict:
        cookies = await self._context.cookies()
        return {c["name"]: c["value"] for c in cookies}

    async def fetch_api(
        self,
        url: str,
        headers: Optional[dict] = None,
        method: str = "GET",
        body: Optional[dict] = None,
    ) -> dict:
        """Run fetch inside the page so credentials/runtime state are inherited."""
        try:
            return await self._page.evaluate(
                """async ({url, headers, method, body}) => {
                    const opts = {method, headers: {'Accept': 'application/json', ...headers}, credentials: 'include'};
                    if (body) { opts.body = JSON.stringify(body); opts.headers['Content-Type'] = 'application/json;charset=UTF-8'; }
                    const resp = await fetch(url, opts);
                    return await resp.json();
                }""",
                {"url": url, "headers": headers or {}, "method": method, "body": body},
            )
        except Exception as e:
            print(f"[Browser fetch error] {e}")
            return {}

    @property
    def page(self):
        return self._page

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.close()
