"""Comments — implemented via browser response interception.

Navigate to the note page (which loads comments); intercept
``/api/sns/web/v2/comment/page`` responses. For sub-comments, scroll down
and intercept ``/api/sns/web/v2/comment/sub/page``.

Also supports explicit fetch via browser.fetch_api for cursor paging.
"""
import asyncio
import time
from typing import List

from models.data import CommentInfo
from config.settings import REQUEST_DELAY

COMMENT_API = "/api/sns/web/v2/comment/page"
SUB_COMMENT_API = "/api/sns/web/v2/comment/sub/page"


def _to_int(v) -> int:
    if isinstance(v, (int, float)):
        return int(v)
    if not v:
        return 0
    s = str(v).strip().replace(",", "")
    try:
        if s.endswith("万"):
            return int(float(s[:-1]) * 10000)
        return int(float(s))
    except ValueError:
        return 0


class CommentScraper:
    def __init__(self, browser):
        self.browser = browser

    async def get_comments(
        self,
        note_id: str,
        xsec_token: str,
        max_count: int = 100,
        xsec_source: str = "pc_search",
    ) -> List[CommentInfo]:
        """Fetch first-level comments for a note via browser response interception.

        Navigates to the note page and intercepts comment API responses as the
        page loads and as we scroll to trigger more loads.
        """
        captured = []

        async def on_response(resp):
            if COMMENT_API in resp.url and SUB_COMMENT_API not in resp.url:
                try:
                    captured.append(await resp.json())
                except Exception:
                    pass

        self.browser.context.on("response", on_response)

        url = (
            f"https://www.xiaohongshu.com/explore/{note_id}"
            f"?xsec_token={xsec_token}&xsec_source={xsec_source}"
        )
        await self.browser.navigate(url)
        await asyncio.sleep(3)

        seen = set()
        comments = []

        max_scrolls = max(max_count // 10, 5)
        for _ in range(max_scrolls):
            batch, captured[:] = list(captured), []
            for r in batch:
                if not isinstance(r, dict):
                    continue
                data = r.get("data") or {}
                for c in data.get("comments", []):
                    cid = c.get("id", "")
                    if not cid or cid in seen:
                        continue
                    seen.add(cid)
                    comments.append(self._parse(c, note_id))
            if len(comments) >= max_count:
                break
            has_more = False
            for r in batch:
                if isinstance(r, dict) and (r.get("data") or {}).get("has_more", False):
                    has_more = True
            if not has_more and len(comments) > 0:
                break
            try:
                await self.browser.page.mouse.wheel(0, 1500)
            except Exception:
                pass
            await asyncio.sleep(REQUEST_DELAY)

        return comments[:max_count]

    async def get_comments_via_api(
        self,
        note_id: str,
        xsec_token: str,
        max_count: int = 100,
        xsec_source: str = "pc_search",
    ) -> List[CommentInfo]:
        """Fetch comments using in-page fetch (cursor paging)."""
        comments = []
        seen = set()
        cursor = ""

        for _ in range(max_count // 20 + 2):
            api_url = (
                f"https://edith.xiaohongshu.com/api/sns/web/v2/comment/page"
                f"?note_id={note_id}&cursor={cursor}&top_comment_id=&image_formats=webp"
                f"&xsec_token={xsec_token}&xsec_source={xsec_source}"
            )
            data = await self.browser.fetch_api(api_url)
            if not data or not isinstance(data, dict):
                break
            inner = data.get("data") or {}
            for c in inner.get("comments", []):
                cid = c.get("id", "")
                if not cid or cid in seen:
                    continue
                seen.add(cid)
                comments.append(self._parse(c, note_id))
            if not inner.get("has_more", False) or len(comments) >= max_count:
                break
            cursor = inner.get("cursor", "")
            if not cursor:
                break
            await asyncio.sleep(REQUEST_DELAY)

        return comments[:max_count]

    async def get_sub_comments(
        self,
        note_id: str,
        root_comment_id: str,
        max_count: int = 50,
        xsec_token: str = "",
    ) -> List[CommentInfo]:
        """Fetch sub-comments (replies) for a first-level comment."""
        comments = []
        seen = set()
        cursor = ""

        for _ in range(max_count // 10 + 2):
            api_url = (
                f"https://edith.xiaohongshu.com/api/sns/web/v2/comment/sub/page"
                f"?note_id={note_id}&root_comment_id={root_comment_id}"
                f"&num=10&cursor={cursor}&image_formats=webp"
            )
            if xsec_token:
                api_url += f"&xsec_token={xsec_token}"
            data = await self.browser.fetch_api(api_url)
            if not data or not isinstance(data, dict):
                break
            inner = data.get("data") or {}
            for c in inner.get("comments", []):
                cid = c.get("id", "")
                if not cid or cid in seen:
                    continue
                seen.add(cid)
                comments.append(self._parse(c, note_id))
            if not inner.get("has_more", False) or len(comments) >= max_count:
                break
            cursor = inner.get("cursor", "")
            if not cursor:
                break
            await asyncio.sleep(REQUEST_DELAY)

        return comments[:max_count]

    def _parse(self, c: dict, note_id: str) -> CommentInfo:
        user = c.get("user_info") or {}
        ct = c.get("create_time") or 0
        if isinstance(ct, (int, float)) and ct > 1000000000:
            ts = ct / 1000 if ct > 10000000000 else ct
            create_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
        else:
            create_time = str(ct) if ct else ""

        target_comment = c.get("target_comment") or {}
        reply_to = target_comment.get("user_info") or {}

        return CommentInfo(
            comment_id=c.get("id", ""),
            note_id=note_id,
            parent_comment_id=target_comment.get("id", ""),
            reply_to_user_id=reply_to.get("user_id", ""),
            reply_to_nickname=reply_to.get("nickname", ""),
            content=c.get("content", ""),
            user_nickname=user.get("nickname", ""),
            user_id=user.get("user_id", ""),
            like_count=_to_int(c.get("like_count")),
            sub_comment_count=_to_int(c.get("sub_comment_count")),
            create_time=create_time,
        )
