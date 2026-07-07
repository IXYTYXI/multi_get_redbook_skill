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
    from models.data import NoteInfo, XhsUserInfo, CommentInfo, LiveBarrageInfo
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
    from scrapers.live import LiveBarrageScraper  # noqa: F401

    note = NoteInfo(note_id="n1", title="t", author_nickname="a", image_urls="")
    user = XhsUserInfo(user_id="u1", nickname="a")
    comment = CommentInfo(comment_id="c1", note_id="n1", content="hi", parent_comment_id="", reply_to_nickname="", reply_to_user_id="")

    assert note_to_feishu_record(note)["标题"] == "t"
    assert user_to_feishu_record(user)["用户ID"] == "u1"
    assert comment_to_feishu_record(comment)["评论ID"] == "c1"

    s, e = date_bounds("2025-01-01", "2025-06-01")
    assert s is not None and e is not None and s < e
    assert in_date_range(None, None, None) is True
    assert download_note_media(note)["cover"] is None

    barrage = LiveBarrageInfo(
        user_id="u1", user_name="test", content="hello",
        message_type="barrage", room_id="r1",
    )
    assert barrage.to_dict()["content"] == "hello"

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


def cmd_note(note_id: str, xsec_token: str) -> int:
    return asyncio.run(_note(note_id, xsec_token))


async def _note(note_id: str, xsec_token: str) -> int:
    from core.browser import XhsBrowser
    from scrapers.note import NoteScraper

    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    async with XhsBrowser() as browser:
        detail = await NoteScraper(browser).get_note(note_id, xsec_token)

    if not detail:
        print(f"Failed to get note {note_id}")
        return 1
    print(f"Title:   {detail.title}")
    print(f"Author:  {detail.author_nickname}")
    print(f"Type:    {detail.note_type}")
    print(f"Likes:   {detail.liked_count}  Collects: {detail.collected_count}  Comments: {detail.comment_count}")
    print(f"Tags:    {detail.tags}")
    print(f"Video:   {detail.video_url or 'N/A'}")
    img_count = len(detail.image_urls.split(",")) if detail.image_urls else 0
    print(f"Images:  {img_count}")
    print(f"Desc:    {detail.desc[:200]}")
    return 0


def cmd_comment(note_id: str, xsec_token: str, n: int) -> int:
    return asyncio.run(_comment(note_id, xsec_token, n))


async def _comment(note_id: str, xsec_token: str, n: int) -> int:
    from core.browser import XhsBrowser
    from scrapers.comment import CommentScraper

    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    async with XhsBrowser() as browser:
        comments = await CommentScraper(browser).get_comments(note_id, xsec_token, max_count=n)

    print(f"\nnote_id={note_id}  got {len(comments)} comments\n")
    for i, c in enumerate(comments, 1):
        print(f"{i:>2}. [{c.user_nickname}] {c.content[:60]}")
        print(f"    likes={c.like_count} replies={c.sub_comment_count} time={c.create_time}")
    return 0 if comments else 1


def cmd_user(user_id: str, xsec_token: str, notes: bool, n: int) -> int:
    return asyncio.run(_user(user_id, xsec_token, notes, n))


async def _user(user_id: str, xsec_token: str, get_notes: bool, n: int) -> int:
    from core.browser import XhsBrowser
    from scrapers.user import UserScraper

    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    async with XhsBrowser() as browser:
        us = UserScraper(browser)
        info = await us.get_user(user_id, xsec_token)
        if not info:
            print(f"Failed to get user {user_id}")
            return 1
        print(f"Nickname:  {info.nickname}")
        print(f"Fans:      {info.fans}")
        print(f"Follows:   {info.follows}")
        print(f"Notes:     {info.note_count}")
        print(f"Desc:      {info.desc[:100]}")

        if get_notes:
            notes_list = await us.get_user_notes(user_id, max_count=n, xsec_token=xsec_token)
            print(f"\n--- User notes ({len(notes_list)}) ---")
            for i, x in enumerate(notes_list, 1):
                print(f"{i:>2}. {x.title[:40]}  likes={x.liked_count}")
    return 0


def cmd_search_user(keyword: str, n: int) -> int:
    return asyncio.run(_search_user(keyword, n))


async def _search_user(keyword: str, n: int) -> int:
    from core.browser import XhsBrowser
    from scrapers.user import UserScraper

    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    async with XhsBrowser() as browser:
        users = await UserScraper(browser).search_users(keyword, max_count=n)

    print(f"\nkeyword='{keyword}'  got {len(users)} users\n")
    for i, u in enumerate(users, 1):
        print(f"{i:>2}. {u.nickname}")
        print(f"    fans={u.fans} notes={u.note_count}")
        print(f"    desc: {u.desc[:60]}")
        print(f"    id={u.user_id}")
    return 0 if users else 1


def cmd_live_barrage(room_url: str, duration: int, output: str) -> int:
    return asyncio.run(_live_barrage(room_url, duration, output))


async def _live_barrage(room_url: str, duration: int, output: str) -> int:
    from scrapers.live import LiveBarrageScraper

    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    dur = duration if duration > 0 else None
    scraper = LiveBarrageScraper()

    def on_msg(msg):
        if output == "json":
            print(json.dumps(msg.to_dict(), ensure_ascii=False))
        else:
            print(f"[{msg.message_type}] {msg.user_name}: {msg.content}")

    messages = await scraper.listen(room_url, duration=dur, on_message=on_msg)
    print(f"\nCaptured {len(messages)} messages total.")
    return 0


def cmd_scrape_all(keyword: str, n: int) -> int:
    from scrape_all import main as sa_main
    return asyncio.run(sa_main(keyword, n))


def main() -> int:
    parser = argparse.ArgumentParser(prog="xhs-scraper")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("check", help="offline smoke test (no network/login)")
    p_login = sub.add_parser("login", help="visible-browser Xiaohongshu login -> cookies.json")
    p_login.add_argument("--timeout", type=int, default=480, help="max seconds to wait for login")
    p_search = sub.add_parser("search", help="keyword note search (needs a saved session)")
    p_search.add_argument("keyword")
    p_search.add_argument("-n", "--max-count", type=int, default=20, dest="n")

    p_note = sub.add_parser("note", help="get note detail by note_id + xsec_token")
    p_note.add_argument("note_id")
    p_note.add_argument("xsec_token")

    p_comment = sub.add_parser("comment", help="get comments for a note")
    p_comment.add_argument("note_id")
    p_comment.add_argument("xsec_token")
    p_comment.add_argument("-n", "--max-count", type=int, default=50, dest="n")

    p_user = sub.add_parser("user", help="get user profile (and optionally their notes)")
    p_user.add_argument("user_id")
    p_user.add_argument("--xsec-token", default="", dest="xsec_token")
    p_user.add_argument("--notes", action="store_true", help="also fetch user's notes")
    p_user.add_argument("-n", "--max-count", type=int, default=30, dest="n")

    p_suser = sub.add_parser("search-user", help="search for users by keyword")
    p_suser.add_argument("keyword")
    p_suser.add_argument("-n", "--max-count", type=int, default=20, dest="n")

    p_live = sub.add_parser("live-barrage", help="capture live-stream barrage messages")
    p_live.add_argument("room_url", help="Xiaohongshu live room URL")
    p_live.add_argument("--duration", type=int, default=0, help="listen duration in seconds (0 = indefinite)")
    p_live.add_argument("--output", choices=["console", "feishu", "json"], default="console", help="output mode")

    p_all = sub.add_parser("scrape-all", help="full pipeline: search -> detail -> comments -> feishu")
    p_all.add_argument("--keyword", "-k", default="")
    p_all.add_argument("-n", "--max-notes", type=int, default=0, dest="n")

    args = parser.parse_args()

    if args.command == "check":
        return cmd_check()
    if args.command == "login":
        return cmd_login(args.timeout)
    if args.command == "search":
        return cmd_search(args.keyword, args.n)
    if args.command == "note":
        return cmd_note(args.note_id, args.xsec_token)
    if args.command == "comment":
        return cmd_comment(args.note_id, args.xsec_token, args.n)
    if args.command == "user":
        return cmd_user(args.user_id, args.xsec_token, args.notes, args.n)
    if args.command == "search-user":
        return cmd_search_user(args.keyword, args.n)
    if args.command == "live-barrage":
        return cmd_live_barrage(args.room_url, args.duration, args.output)
    if args.command == "scrape-all":
        return cmd_scrape_all(args.keyword, args.n)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
