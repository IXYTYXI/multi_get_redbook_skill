#!/usr/bin/env python3
"""xhs-scraper CLI entry point.

Commands:
  check    offline smoke test (no network/login)
  login    open a visible browser, log into Xiaohongshu, save cookies.json + .env
  search   keyword note search  -> Feishu bitable or local json/csv
  note     single note detail (needs note_id + xsec_token)
  comment  comments of a note   (needs note_id + xsec_token)
  user     author profile + notes

search / note / comment / user require a logged-in session (run `login` first,
or set XHS_COOKIE). XHS signs every web API call — see core/sign.py.
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(errors="replace")  # Windows GBK console safety
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass


# --------------------------------------------------------------------------- #
# check (offline)
# --------------------------------------------------------------------------- #
def cmd_check() -> int:
    """Offline smoke test: build models, exercise parsers/date filter, import all."""
    from models.data import NoteInfo, XhsUserInfo, CommentInfo
    from core.datefilter import date_bounds, in_date_range
    from storage.feishu import (
        note_to_feishu_record,
        user_to_feishu_record,
        comment_to_feishu_record,
    )
    from storage.downloader import download_note_media
    from storage.local import LocalStorage  # noqa: F401
    import core.browser  # noqa: F401
    from core.sign import build_x_s_common, _mrc
    from core.client import XhsClient  # noqa: F401
    from scrapers.keyword import KeywordScraper, parse_item, to_int, new_search_id
    from scrapers.note import NoteScraper, parse_note_card
    from scrapers.comment import CommentScraper, parse_comment
    from scrapers.user import UserScraper, parse_user, parse_posted_note

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

    # --- Stage 1 signing (pure, offline pieces) ---
    assert to_int("1.2万") == 12000 and to_int("3000") == 3000 and to_int("") == 0
    assert isinstance(_mrc("abc"), int)
    xsc = build_x_s_common("a1v", "b1v", "xsv", "1700000000000")
    assert isinstance(xsc, str) and len(xsc) > 0
    assert len(new_search_id()) > 0

    # --- Stage 2 parsers (fixtures shaped like the real API) ---
    parsed = parse_item({
        "id": "n9", "xsec_token": "tok",
        "note_card": {
            "type": "normal", "display_title": "标题",
            "user": {"nickname": "作者", "user_id": "u9"},
            "interact_info": {"liked_count": "1.2万", "comment_count": "8"},
            "cover": {"url_default": "http://c"},
        },
    })
    assert parsed.note_id == "n9" and parsed.liked_count == 12000
    assert parsed.xsec_token == "tok" and "xsec_token=tok" in parsed.note_url
    assert parse_item({"model_type": "rec_query", "id": ""}) is None

    detail = parse_note_card("n9", {
        "type": "video", "title": "T", "desc": "d",
        "user": {"nickname": "作者", "user_id": "u9"},
        "interact_info": {"liked_count": 10, "collected_count": 2},
        "image_list": [{"info_list": [{"image_scene": "WB_DFT", "url": "http://i"}]}],
        "tag_list": [{"name": "护肤"}],
        "time": 1700000000000,
    }, "tok", "pc_search")
    assert detail.image_urls == "http://i" and detail.tags == "护肤"
    assert detail.create_time.startswith("20")

    c = parse_comment("n9", {
        "id": "c9", "content": "nice", "like_count": "3",
        "user_info": {"nickname": "路人", "user_id": "u2"}, "create_time": 1700000000000,
    })
    assert c.comment_id == "c9" and c.like_count == 3

    u = parse_user("u9", {
        "basic_info": {"nickname": "作者", "desc": "hi"},
        "interactions": [{"type": "fans", "count": "100"}, {"type": "follows", "count": "5"}],
    })
    assert u.fans == 100 and u.follows == 5 and u.user_id == "u9"

    pn = parse_posted_note("u9", {
        "note_id": "n8", "xsec_token": "t2",
        "note_card": {"display_title": "x", "interact_info": {"liked_count": 7},
                      "cover": {"url_default": "http://c2"}},
    })
    assert pn.note_id == "n8" and pn.liked_count == 7 and pn.xsec_source == "pc_user"

    print("xhs-scraper scaffold OK")
    return 0


# --------------------------------------------------------------------------- #
# login
# --------------------------------------------------------------------------- #
def _save_cookie_to_env(cookie_str: str):
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
    return asyncio.run(_login(timeout))


async def _login(timeout: int = 480) -> int:
    import time as _t
    from playwright.async_api import async_playwright
    from core.browser import COOKIE_FILE, STEALTH_JS

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
        print("\n✅ 检测到登录，Cookie 已保存到 cookies.json 和 .env。")
        return 0
    print("\n⚠️ 超时未检测到登录。已尽量保存当前 Cookie；如未登录请重试。")
    return 1


# --------------------------------------------------------------------------- #
# scraping commands (Stage 2/3)
# --------------------------------------------------------------------------- #
async def _open_session(headless: bool):
    """Start a logged-in browser + signed client; abort clearly if not logged in."""
    from core.browser import XhsBrowser
    from core.client import XhsClient

    browser = XhsBrowser()
    await browser.start(headless=headless)
    await browser.navigate("https://www.xiaohongshu.com")
    jar = await browser.cookie_dict()
    if len(jar.get("web_session", "")) <= 20 or not jar.get("a1"):
        await browser.close()
        raise SystemExit(
            "未检测到有效登录态（缺少 web_session / a1）。\n"
            "小红书所有接口都需要登录 + 签名，无法在未登录下联调。\n"
            "请先运行 `python main.py login` 扫码登录，或设置有效的 XHS_COOKIE。"
        )
    return browser, XhsClient(browser)


def _output(records, name: str, table_env_key: str, save_local: bool):
    """Write to Feishu when configured & requested, else local json/csv."""
    from config.settings import FEISHU_APP_ID
    from storage.local import LocalStorage
    if not records:
        print("没有数据可输出。")
        return

    wrote_feishu = False
    table_id = os.getenv(table_env_key, "")
    if FEISHU_APP_ID and table_id and not save_local:
        try:
            from storage.feishu import (
                FeishuBitable, note_to_feishu_record,
                user_to_feishu_record, comment_to_feishu_record,
            )
            conv = {
                "NOTE_TABLE_ID": note_to_feishu_record,
                "USER_TABLE_ID": user_to_feishu_record,
                "COMMENT_TABLE_ID": comment_to_feishu_record,
            }[table_env_key]
            feishu = FeishuBitable(table_id=table_id)
            feishu.write_records([conv(_Obj(r)) for r in records], table_id)
            feishu.close()
            wrote_feishu = True
        except Exception as e:
            print(f"飞书写入失败: {e}，回退到本地存储。")

    if not wrote_feishu:
        local = LocalStorage()
        local.save_json(records, f"{name}.json")
        local.save_csv(records, f"{name}.csv")


class _Obj:
    """Wrap a dict so the feishu record converters (attr access) work uniformly."""
    def __init__(self, d):
        self.__dict__.update(d)


def cmd_search(args) -> int:
    return asyncio.run(_run_search(args))


async def _run_search(args) -> int:
    from scrapers.keyword import KeywordScraper
    from scrapers.note import NoteScraper
    from scrapers.comment import CommentScraper

    browser, client = await _open_session(headless=not args.no_headless)
    try:
        notes = await KeywordScraper(client).search_notes(args.keyword, args.max_count)
        if args.detail:  # enrich each with full note detail (uses xsec_token)
            note_scraper = NoteScraper(client)
            enriched = []
            for n in notes:
                d = await note_scraper.get_note(n.note_id, n.xsec_token, n.xsec_source)
                enriched.append(d or n)
            notes = enriched
        records = [n.to_dict() for n in notes]
        _output(records, f"search_{args.keyword}", "NOTE_TABLE_ID", args.local)

        if args.comments and notes:
            cs = CommentScraper(client)
            all_c = []
            for n in notes[: args.comment_notes]:
                all_c += [c.to_dict() for c in await cs.get_comments(
                    n.note_id, n.xsec_token, args.max_comments)]
            _output(all_c, f"comments_{args.keyword}", "COMMENT_TABLE_ID", args.local)
    finally:
        await browser.close()
    return 0


def cmd_note(args) -> int:
    return asyncio.run(_run_note(args))


async def _run_note(args) -> int:
    from scrapers.note import NoteScraper
    browser, client = await _open_session(headless=not args.no_headless)
    try:
        note = await NoteScraper(client).get_note(args.note_id, args.xsec_token, args.xsec_source)
        if note:
            print(f"\n{note.title}\n点赞 {note.liked_count} | 收藏 {note.collected_count} "
                  f"| 评论 {note.comment_count}")
            _output([note.to_dict()], f"note_{args.note_id}", "NOTE_TABLE_ID", args.local)
    finally:
        await browser.close()
    return 0


def cmd_comment(args) -> int:
    return asyncio.run(_run_comment(args))


async def _run_comment(args) -> int:
    from scrapers.comment import CommentScraper
    browser, client = await _open_session(headless=not args.no_headless)
    try:
        comments = await CommentScraper(client).get_comments(
            args.note_id, args.xsec_token, args.max_count)
        _output([c.to_dict() for c in comments], f"comments_{args.note_id}",
                "COMMENT_TABLE_ID", args.local)
    finally:
        await browser.close()
    return 0


def cmd_user(args) -> int:
    return asyncio.run(_run_user(args))


async def _run_user(args) -> int:
    from scrapers.user import UserScraper
    browser, client = await _open_session(headless=not args.no_headless)
    try:
        us = UserScraper(client)
        user = await us.get_user(args.user_id, args.xsec_token)
        print(f"\n{user.nickname} | 粉丝 {user.fans} | 笔记 {user.note_count}")
        _output([user.to_dict()], f"user_{args.user_id}", "USER_TABLE_ID", args.local)
        if not args.info_only:
            notes = await us.get_user_notes(args.user_id, args.max_notes, args.xsec_token)
            _output([n.to_dict() for n in notes], f"user_notes_{args.user_id}",
                    "NOTE_TABLE_ID", args.local)
    finally:
        await browser.close()
    return 0


# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(prog="xhs-scraper")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("check", help="offline smoke test (no network/login)")

    p_login = sub.add_parser("login", help="visible-browser Xiaohongshu login -> cookies.json")
    p_login.add_argument("--timeout", type=int, default=480, help="max seconds to wait for login")

    def _common(p):
        p.add_argument("--no-headless", action="store_true", help="show the browser (pass captcha)")
        p.add_argument("--local", action="store_true", help="force local json/csv output")

    p_s = sub.add_parser("search", help="keyword note search")
    p_s.add_argument("keyword")
    p_s.add_argument("-n", "--max-count", type=int, default=30)
    p_s.add_argument("--detail", action="store_true", help="fetch full note detail per result")
    p_s.add_argument("--comments", action="store_true", help="also fetch comments")
    p_s.add_argument("--comment-notes", type=int, default=5, help="how many notes to comment-scrape")
    p_s.add_argument("--max-comments", type=int, default=50)
    _common(p_s)

    p_n = sub.add_parser("note", help="single note detail")
    p_n.add_argument("note_id")
    p_n.add_argument("xsec_token")
    p_n.add_argument("--xsec-source", default="pc_search")
    _common(p_n)

    p_c = sub.add_parser("comment", help="comments of a note")
    p_c.add_argument("note_id")
    p_c.add_argument("xsec_token")
    p_c.add_argument("-n", "--max-count", type=int, default=100)
    _common(p_c)

    p_u = sub.add_parser("user", help="author profile + notes")
    p_u.add_argument("user_id")
    p_u.add_argument("--xsec-token", default="")
    p_u.add_argument("--info-only", action="store_true")
    p_u.add_argument("--max-notes", type=int, default=30)
    _common(p_u)

    args = parser.parse_args()
    if args.command == "check":
        return cmd_check()
    if args.command == "login":
        return cmd_login(args.timeout)
    if args.command == "search":
        return cmd_search(args)
    if args.command == "note":
        return cmd_note(args)
    if args.command == "comment":
        return cmd_comment(args)
    if args.command == "user":
        return cmd_user(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
