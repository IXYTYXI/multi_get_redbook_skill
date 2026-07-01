"""Note keyword search.

Endpoint: ``POST /api/sns/web/v1/search/notes``. Each result carries a per-note
``xsec_token`` (with ``xsec_source=pc_search``) that MUST be captured and threaded
into note-detail and comment requests — a bare ``note_id`` triggers risk-control
300017.

The network call goes through the signed :class:`core.client.XhsClient`; the
pure parsing (:meth:`parse_item`) is separated so it can be smoke-tested offline.
"""
import secrets
import time
from typing import List, Optional

from config.settings import MAX_PAGES, XHS_BASE_URL
from models.data import NoteInfo

SEARCH_URI = "/api/sns/web/v1/search/notes"


def new_search_id() -> str:
    """Approximate XHS's client search_id: base-36 of (ms<<64 | rand)."""
    value = (int(time.time() * 1000) << 64) + secrets.randbelow(2**64)
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    if value == 0:
        return "0"
    out = []
    while value:
        value, rem = divmod(value, 36)
        out.append(digits[rem])
    return "".join(reversed(out))


def to_int(value) -> int:
    """XHS counts arrive as int or strings like '1.2万' / '3000'."""
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip().replace(",", "")
    if not s:
        return 0
    try:
        if s.endswith("万"):
            return int(float(s[:-1]) * 10000)
        if s.endswith("亿"):
            return int(float(s[:-1]) * 100000000)
        return int(float(s))
    except ValueError:
        return 0


def parse_item(item: dict) -> Optional[NoteInfo]:
    """Parse one search ``items[]`` entry into a NoteInfo, or None if not a note."""
    card = item.get("note_card") or item.get("noteCard") or {}
    note_id = item.get("id") or card.get("note_id") or ""
    if not card or not note_id:
        return None  # skip non-note rows (rec-query words, ads, hot-words)

    user = card.get("user") or {}
    interact = card.get("interact_info") or card.get("interactInfo") or {}
    cover = card.get("cover") or {}
    cover_url = ""
    if isinstance(cover, dict):
        cover_url = cover.get("url_default") or cover.get("url_pre") or cover.get("url") or ""

    xsec_token = item.get("xsec_token") or card.get("xsec_token") or ""
    note_url = f"{XHS_BASE_URL}/explore/{note_id}"
    if xsec_token:
        note_url += f"?xsec_token={xsec_token}&xsec_source=pc_search"

    return NoteInfo(
        note_id=note_id,
        xsec_token=xsec_token,
        xsec_source="pc_search",
        note_type=card.get("type", ""),
        title=card.get("display_title") or card.get("displayTitle") or "",
        desc=card.get("desc", ""),
        author_nickname=user.get("nickname") or user.get("nick_name") or "",
        author_user_id=user.get("user_id") or user.get("userId") or "",
        liked_count=to_int(interact.get("liked_count") or interact.get("likedCount")),
        collected_count=to_int(interact.get("collected_count") or interact.get("collectedCount")),
        comment_count=to_int(interact.get("comment_count") or interact.get("commentCount")),
        share_count=to_int(interact.get("shared_count") or interact.get("share_count")),
        cover_url=cover_url,
        note_url=note_url,
    )


class KeywordScraper:
    """Search notes by keyword through the signed client."""

    def __init__(self, client=None):
        self.client = client

    async def search_notes(self, keyword: str, max_count: int = 50) -> List[NoteInfo]:
        results: List[NoteInfo] = []
        seen = set()
        search_id = new_search_id()
        page = 1

        while len(results) < max_count and page <= MAX_PAGES:
            payload = {
                "keyword": keyword,
                "page": page,
                "page_size": 20,
                "search_id": search_id,
                "sort": "general",
                "note_type": 0,
                "ext_flags": [],
                "image_formats": ["jpg", "webp", "avif"],
            }
            data = await self.client.post(SEARCH_URI, payload)
            items = data.get("items", []) or []
            if not items:
                break

            for item in items:
                note = parse_item(item)
                if note is None or note.note_id in seen:
                    continue
                seen.add(note.note_id)
                results.append(note)
                if len(results) >= max_count:
                    break

            if not data.get("has_more"):
                break
            page += 1

        print(f"[Search] Found {len(results)} notes for keyword '{keyword}'")
        return results[:max_count]
