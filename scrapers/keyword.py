"""Note keyword search — implemented via browser response interception.

The logged-in page issues its own signed request to
``/api/sns/web/v2/search/notes``; we simply capture the JSON responses (so no
signature reimplementation is needed) and parse them into ``NoteInfo``. Each
result carries a per-note ``xsec_token`` used later for detail/comments.
"""
import asyncio
from urllib.parse import quote
from typing import List

from models.data import NoteInfo

SEARCH_API = "/api/sns/web/v2/search/notes"


def _to_int(v) -> int:
    """XHS counts come as ints or strings like '1.2万' / '1,234'."""
    if isinstance(v, (int, float)):
        return int(v)
    if not v:
        return 0
    s = str(v).strip().replace(",", "")
    try:
        if s.endswith("万"):
            return int(float(s[:-1]) * 10000)
        if s.endswith("亿"):
            return int(float(s[:-1]) * 100000000)
        return int(float(s))
    except ValueError:
        return 0


class KeywordScraper:
    def __init__(self, browser):
        self.browser = browser  # XhsBrowser (logged-in)

    async def search_notes(
        self, keyword: str, max_count: int = 20, max_scrolls: int = 8
    ) -> List[NoteInfo]:
        captured = []

        async def on_response(resp):
            if SEARCH_API in resp.url:
                try:
                    captured.append(await resp.json())
                except Exception:
                    pass

        self.browser.context.on("response", on_response)

        url = (
            f"https://www.xiaohongshu.com/search_result"
            f"?keyword={quote(keyword)}&source=web_explore_feed"
        )
        await self.browser.navigate(url)

        seen, notes = set(), []
        for _ in range(max_scrolls):
            await asyncio.sleep(2)
            batch, captured[:] = list(captured), []
            for r in batch:
                if not isinstance(r, dict):
                    continue
                for it in (r.get("data") or {}).get("items", []):
                    nid = it.get("id")
                    nc = it.get("note_card")
                    if not nid or nid in seen or not nc:
                        continue
                    seen.add(nid)
                    notes.append(self._parse(it))
            if len(notes) >= max_count:
                break
            try:
                await self.browser.page.mouse.wheel(0, 2500)
            except Exception:
                pass

        return notes[:max_count]

    def _parse(self, it: dict) -> NoteInfo:
        nc = it.get("note_card", {}) or {}
        user = nc.get("user", {}) or {}
        interact = nc.get("interact_info", {}) or {}
        cover = nc.get("cover", {}) or {}
        cover_url = cover.get("url_default") or cover.get("url_pre") or ""
        nid = it.get("id", "")
        token = it.get("xsec_token", "")
        return NoteInfo(
            note_id=nid,
            xsec_token=token,
            xsec_source="pc_search",
            note_type=nc.get("type", ""),
            title=nc.get("display_title", ""),
            author_nickname=user.get("nick_name") or user.get("nickname", ""),
            author_user_id=user.get("user_id", ""),
            liked_count=_to_int(interact.get("liked_count")),
            collected_count=_to_int(interact.get("collected_count")),
            comment_count=_to_int(interact.get("comment_count")),
            share_count=_to_int(interact.get("shared_count")),
            cover_url=cover_url,
            note_url=(
                f"https://www.xiaohongshu.com/explore/{nid}"
                f"?xsec_token={token}&xsec_source=pc_search"
                if nid else ""
            ),
        )
