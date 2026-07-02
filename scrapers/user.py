"""Author profile, user search, and their notes — via browser response interception.

Navigate to the user's profile page; intercept:
  - ``/api/sns/web/v1/user/otherinfo`` for profile data
  - ``/api/sns/web/v1/user_posted`` for their note list (carries xsec_token)
  - ``/api/sns/web/v1/search/user_info`` for user search results
"""
import asyncio
from urllib.parse import quote
from typing import List, Optional

from models.data import NoteInfo, XhsUserInfo
from scrapers.keyword import _to_int
from config.settings import REQUEST_DELAY

USER_INFO_API = "/api/sns/web/v1/user/otherinfo"
USER_POSTED_API = "/api/sns/web/v1/user_posted"
USER_SEARCH_API = "/api/sns/web/v1/search/user_info"


class UserScraper:
    def __init__(self, browser):
        self.browser = browser

    async def search_users(
        self, keyword: str, max_count: int = 20, max_scrolls: int = 8
    ) -> List[XhsUserInfo]:
        captured = []

        async def on_response(resp):
            if USER_SEARCH_API in resp.url:
                try:
                    captured.append(await resp.json())
                except Exception:
                    pass

        self.browser.context.on("response", on_response)

        url = (
            f"https://www.xiaohongshu.com/search_result"
            f"?keyword={quote(keyword)}&source=web_search_result_page&type=user"
        )
        await self.browser.navigate(url)

        seen, users = set(), []
        for _ in range(max_scrolls):
            await asyncio.sleep(2)
            batch, captured[:] = list(captured), []
            for r in batch:
                if not isinstance(r, dict):
                    continue
                for it in (r.get("data") or {}).get("users", []):
                    uid = it.get("user_id") or it.get("id", "")
                    if not uid or uid in seen:
                        continue
                    seen.add(uid)
                    users.append(self._parse_search_user(it))
            if len(users) >= max_count:
                break
            try:
                await self.browser.page.mouse.wheel(0, 2500)
            except Exception:
                pass

        return users[:max_count]

    def _parse_search_user(self, it: dict) -> XhsUserInfo:
        uid = it.get("user_id") or it.get("id", "")
        return XhsUserInfo(
            user_id=uid,
            xsec_token=it.get("xsec_token", ""),
            nickname=it.get("nickname") or it.get("nick_name", ""),
            desc=it.get("desc", ""),
            fans=_to_int(it.get("fans") or it.get("fansCount")),
            note_count=_to_int(it.get("note_count") or it.get("noteCount")),
            avatar_url=it.get("image") or it.get("imageb", ""),
            homepage_url=f"https://www.xiaohongshu.com/user/profile/{uid}",
        )

    async def get_user(
        self,
        user_id: str,
        xsec_token: str = "",
        xsec_source: str = "pc_user",
    ) -> Optional[XhsUserInfo]:
        captured_info = []

        async def on_response(resp):
            if USER_INFO_API in resp.url:
                try:
                    captured_info.append(await resp.json())
                except Exception:
                    pass

        self.browser.context.on("response", on_response)

        url = f"https://www.xiaohongshu.com/user/profile/{user_id}"
        if xsec_token:
            url += f"?xsec_token={xsec_token}&xsec_source={xsec_source}"
        await self.browser.navigate(url)
        await asyncio.sleep(3)

        for r in captured_info:
            if not isinstance(r, dict):
                continue
            data = r.get("data") or {}
            basic = data.get("basic_info") or {}
            interactions = data.get("interactions") or []
            inter_map = {}
            for item in interactions:
                inter_map[item.get("type", "")] = _to_int(item.get("count"))
            return XhsUserInfo(
                user_id=user_id,
                xsec_token=xsec_token,
                nickname=basic.get("nickname", ""),
                desc=basic.get("desc", ""),
                fans=inter_map.get("fans", 0),
                follows=inter_map.get("follows", 0),
                interaction=inter_map.get("interaction", 0),
                note_count=_to_int(data.get("note_count")),
                avatar_url=basic.get("imageb", "") or basic.get("image", ""),
                homepage_url=f"https://www.xiaohongshu.com/user/profile/{user_id}",
            )

        return None

    async def get_user_notes(
        self,
        user_id: str,
        max_count: int = 50,
        xsec_token: str = "",
        xsec_source: str = "pc_user",
    ) -> List[NoteInfo]:
        captured = []

        async def on_response(resp):
            if USER_POSTED_API in resp.url:
                try:
                    captured.append(await resp.json())
                except Exception:
                    pass

        self.browser.context.on("response", on_response)

        url = f"https://www.xiaohongshu.com/user/profile/{user_id}"
        if xsec_token:
            url += f"?xsec_token={xsec_token}&xsec_source={xsec_source}"
        await self.browser.navigate(url)
        await asyncio.sleep(3)

        seen = set()
        notes = []

        max_scrolls = max(max_count // 15, 5)
        for _ in range(max_scrolls):
            batch, captured[:] = list(captured), []
            for r in batch:
                if not isinstance(r, dict):
                    continue
                data = r.get("data") or {}
                for it in data.get("notes", []):
                    nid = it.get("note_id", "")
                    if not nid or nid in seen:
                        continue
                    seen.add(nid)
                    notes.append(self._parse_note(it, user_id))
            if len(notes) >= max_count:
                break
            has_more = any(
                isinstance(r, dict) and (r.get("data") or {}).get("has_more", False)
                for r in batch
            )
            if not has_more and notes:
                break
            try:
                await self.browser.page.mouse.wheel(0, 2000)
            except Exception:
                pass
            await asyncio.sleep(REQUEST_DELAY)

        return notes[:max_count]

    def _parse_note(self, it: dict, user_id: str) -> NoteInfo:
        display = it.get("display_title", "")
        cover = it.get("cover", {}) or {}
        cover_url = cover.get("url_default") or cover.get("url_pre") or ""
        nid = it.get("note_id", "")
        token = it.get("xsec_token", "")
        interact = it.get("interact_info", {}) or {}
        user = it.get("user", {}) or {}
        return NoteInfo(
            note_id=nid,
            xsec_token=token,
            xsec_source="pc_user",
            note_type=it.get("type", ""),
            title=display,
            author_nickname=user.get("nick_name") or user.get("nickname", ""),
            author_user_id=user.get("user_id") or user_id,
            liked_count=_to_int(interact.get("liked_count")),
            cover_url=cover_url,
            note_url=(
                f"https://www.xiaohongshu.com/explore/{nid}"
                f"?xsec_token={token}&xsec_source=pc_user"
                if nid else ""
            ),
        )
