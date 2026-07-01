#!/usr/bin/env python3
"""xhs-scraper CLI entry point.

Commands:
  check   offline smoke test (no network/login)
  login   open a visible browser, log into Xiaohongshu, save cookies.json + .env
          (same pattern as douyin-scraper; run this on the desktop runtime)

Search/user/note/comment land in Stage 2 (they use the saved login session).
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def cmd_check() -> int:
    """Offline smoke test: build models, exercise date filter, import modules."""
    from models.data import NoteInfo, XhsUserInfo, CommentInfo
    from core.datefilter import date_bounds, in_date_range
    from storage.feishu import (
        note_to_feishu_record,
        user_to_feishu_record,
        comment_to_feishu_record,
    )
    from storage.downloader import download_note_media
    import core.sign  # noqa: F401  (import-only; signing lands in Stage 1)
    import core.browser  # noqa: F401
    from scrapers.keyword import KeywordScraper  # noqa: F401
    from scrapers.note import NoteScraper  # noqa: F401
    from scrapers.comment import CommentScraper  # noqa: F401
    from scrapers.user import UserScraper  # noqa: F401

    note = NoteInfo(note_id="n1", title="t", author_nickname="a", image_urls="")
    user = XhsUserInfo(user_id="u1", nickname="a")
    comment = CommentInfo(comment_id="c1", note_id="n1", content="hi")

    assert note_to_feishu_record(note)["标题"] == "t"
    assert user_to_feishu_record(user)["用户ID"] == "u1"
    assert comment_to_feishu_record(comment)["评论ID"] == "c1"

    s, e = date_bounds("2025-01-01", "2025-06-01")
    assert s is not None and e is not None and s < e
    assert in_date_range(None, None, None) is True
    assert download_note_media(note)["cover"] is None

    print("xhs-scraper scaffold OK")
    return 0


def _save_cookie_to_env(cookie_str: str):
    """Write/replace XHS_COOKIE in the skill-root .env (preserving other keys)."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    out, done = [], False
    for ln in lines:
        if ln.startswith("XHS_COOKIE="):
            out.append("XHS_COOKIE=" + cookie_str)
            done = True
        else:
            out.append(ln)
    if not done:
        out.append("XHS_COOKIE=" + cookie_str)
    with open(env_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")


def cmd_login(timeout: int = 480) -> int:
    """Open a visible browser to log into Xiaohongshu; save cookies.json + .env."""
    return asyncio.run(_login(timeout))


async def _login(timeout: int = 480) -> int:
    import time as _t
    from playwright.async_api import async_playwright
    from core.browser import COOKIE_FILE, STEALTH_JS

    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    pw = await async_playwright().start()
    br = await pw.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )
    ctx = await br.new_context(
        viewport={"width": 1440, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
    )
    await ctx.add_init_script(STEALTH_JS)
    page = await ctx.new_page()
    try:
        await page.goto("https://www.xiaohongshu.com", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass

    print("浏览器已打开。请在窗口里登录小红书（扫码或手机号），并完成任何验证。")
    print(f"检测到登录后会自动保存 Cookie；最多等待 {timeout} 秒。")

    def cookie_str(cookies):
        return "; ".join(f"{c['name']}={c['value']}" for c in cookies)

    def is_logged_in(cookies):
        by = {c["name"]: c["value"] for c in cookies}
        # web_session is short/empty when logged out, a long token once logged in.
        return len(by.get("web_session", "")) > 20

    start = _t.time()
    logged_in = False
    last_str = ""
    while _t.time() - start < timeout:
        await asyncio.sleep(5)
        cookies = await ctx.cookies()
        last_str = cookie_str(cookies)
        if last_str:
            with open(COOKIE_FILE, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            _save_cookie_to_env(last_str)
        if is_logged_in(cookies):
            logged_in = True
            await asyncio.sleep(3)
            cookies = await ctx.cookies()
            with open(COOKIE_FILE, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            _save_cookie_to_env(cookie_str(cookies))
            break

    await br.close()
    await pw.stop()
    if logged_in:
        print(f"\n✅ 检测到登录，Cookie 已保存到 cookies.json 和 .env。")
        return 0
    print("\n⚠️ 超时未检测到登录。已尽量保存当前 Cookie；如未登录请重试。")
    return 1


def cmd_search(keyword: str, n: int) -> int:
    return asyncio.run(_search(keyword, n))


async def _search(keyword: str, n: int) -> int:
    from core.browser import XhsBrowser
    from scrapers.keyword import KeywordScraper

    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    async with XhsBrowser() as browser:
        notes = await KeywordScraper(browser).search_notes(keyword, max_count=n)

    print(f"\nkeyword='{keyword}'  got {len(notes)} notes\n")
    for i, x in enumerate(notes, 1):
        print(f"{i:>2}. [{x.note_type}] {x.title[:36]}")
        print(f"    by {x.author_nickname} | 赞{x.liked_count} 藏{x.collected_count} 评{x.comment_count}")
        print(f"    id={x.note_id} token={'yes' if x.xsec_token else 'no'}")
    return 0 if notes else 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="xhs-scraper")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("check", help="offline smoke test (no network/login)")
    p_login = sub.add_parser("login", help="visible-browser Xiaohongshu login -> cookies.json")
    p_login.add_argument("--timeout", type=int, default=480, help="max seconds to wait for login")
    p_search = sub.add_parser("search", help="keyword note search (needs a saved session)")
    p_search.add_argument("keyword")
    p_search.add_argument("-n", "--max-count", type=int, default=20, dest="n")
    args = parser.parse_args()

    if args.command == "check":
        return cmd_check()
    if args.command == "login":
        return cmd_login(args.timeout)
    if args.command == "search":
        return cmd_search(args.keyword, args.n)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
