"""Comments.

Endpoints: ``GET /api/sns/web/v2/comment/page`` (first-level, cursor paging) and
``GET /api/sns/web/v2/comment/sub/page`` (sub-comments). Both require ``note_id``
+ ``xsec_token`` from the search/list response.
"""
import time
from typing import List

from config.settings import MAX_PAGES
from models.data import CommentInfo
from scrapers.keyword import to_int

COMMENT_URI = "/api/sns/web/v2/comment/page"


def _fmt_time(ms) -> str:
    try:
        ts = int(ms)
    except (TypeError, ValueError):
        return ""
    if ts <= 0:
        return ""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts / 1000))


def parse_comment(note_id: str, raw: dict) -> CommentInfo:
    """Parse one comment object into CommentInfo."""
    user = raw.get("user_info") or {}
    return CommentInfo(
        comment_id=raw.get("id", ""),
        note_id=note_id,
        content=raw.get("content", ""),
        user_nickname=user.get("nickname") or user.get("nick_name") or "",
        user_id=user.get("user_id", ""),
        like_count=to_int(raw.get("like_count")),
        sub_comment_count=to_int(raw.get("sub_comment_count")),
        create_time=_fmt_time(raw.get("create_time")),
    )


class CommentScraper:
    def __init__(self, client=None):
        self.client = client

    async def get_comments(
        self, note_id: str, xsec_token: str, max_count: int = 100
    ) -> List[CommentInfo]:
        results: List[CommentInfo] = []
        cursor = ""
        pages = 0

        while len(results) < max_count and pages < MAX_PAGES:
            params = {
                "note_id": note_id,
                "cursor": cursor,
                "top_comment_id": "",
                "image_formats": "jpg,webp,avif",
                "xsec_token": xsec_token,
            }
            data = await self.client.get(COMMENT_URI, params)
            comments = data.get("comments", []) or []
            if not comments:
                break

            for raw in comments:
                results.append(parse_comment(note_id, raw))
                if len(results) >= max_count:
                    break

            cursor = data.get("cursor", "")
            pages += 1
            if not data.get("has_more") or not cursor:
                break

        print(f"[Comment] Found {len(results)} comments for note {note_id}")
        return results[:max_count]
