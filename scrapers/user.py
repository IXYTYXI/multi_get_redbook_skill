"""Author profile + their notes.

Endpoints: ``GET /api/sns/web/v1/user/otherinfo`` (profile) and
``GET /api/sns/web/v1/user_posted`` (their notes; each carries a per-note
``xsec_token``).
"""
from typing import List, Optional

from config.settings import MAX_PAGES, XHS_BASE_URL
from models.data import NoteInfo, XhsUserInfo
from scrapers.keyword import to_int

OTHERINFO_URI = "/api/sns/web/v1/user/otherinfo"
USER_POSTED_URI = "/api/sns/web/v1/user_posted"


def parse_user(user_id: str, data: dict) -> XhsUserInfo:
    """Parse an otherinfo ``data`` block into XhsUserInfo."""
    basic = data.get("basic_info") or {}
    interactions = {i.get("type"): i.get("count") for i in data.get("interactions", []) or []}
    return XhsUserInfo(
        user_id=user_id,
        nickname=basic.get("nickname") or basic.get("nick_name") or "",
        desc=basic.get("desc", ""),
        fans=to_int(interactions.get("fans")),
        follows=to_int(interactions.get("follows")),
        interaction=to_int(interactions.get("interaction")),
        note_count=to_int((data.get("tab_public") or {}).get("collection")),
        avatar_url=basic.get("images", ""),
        homepage_url=f"{XHS_BASE_URL}/user/profile/{user_id}",
    )


def parse_posted_note(user_id: str, raw: dict) -> Optional[NoteInfo]:
    """Parse one ``user_posted.notes[]`` entry into NoteInfo."""
    note_id = raw.get("note_id") or raw.get("id") or ""
    if not note_id:
        return None
    card = raw.get("note_card") or raw
    interact = card.get("interact_info") or {}
    cover = card.get("cover") or {}
    xsec_token = raw.get("xsec_token") or card.get("xsec_token") or ""
    note_url = f"{XHS_BASE_URL}/explore/{note_id}"
    if xsec_token:
        note_url += f"?xsec_token={xsec_token}&xsec_source=pc_user"
    return NoteInfo(
        note_id=note_id,
        xsec_token=xsec_token,
        xsec_source="pc_user",
        note_type=card.get("type", ""),
        title=card.get("display_title") or card.get("title") or "",
        author_user_id=user_id,
        liked_count=to_int(interact.get("liked_count")),
        cover_url=cover.get("url_default") or cover.get("url") or "",
        note_url=note_url,
    )


class UserScraper:
    def __init__(self, client=None):
        self.client = client

    async def get_user(
        self, user_id: str, xsec_token: str = "", xsec_source: str = "pc_user"
    ) -> XhsUserInfo:
        params = {"target_user_id": user_id}
        if xsec_token:
            params["xsec_token"] = xsec_token
            params["xsec_source"] = xsec_source
        data = await self.client.get(OTHERINFO_URI, params)
        return parse_user(user_id, data)

    async def get_user_notes(
        self, user_id: str, max_count: int = 50, xsec_token: str = ""
    ) -> List[NoteInfo]:
        results: List[NoteInfo] = []
        cursor = ""
        pages = 0
        while len(results) < max_count and pages < MAX_PAGES:
            params = {
                "num": 30,
                "cursor": cursor,
                "user_id": user_id,
                "image_formats": "jpg,webp,avif",
            }
            if xsec_token:
                params["xsec_token"] = xsec_token
                params["xsec_source"] = "pc_user"
            data = await self.client.get(USER_POSTED_URI, params)
            notes = data.get("notes", []) or []
            if not notes:
                break
            for raw in notes:
                note = parse_posted_note(user_id, raw)
                if note:
                    results.append(note)
                    if len(results) >= max_count:
                        break
            cursor = data.get("cursor", "")
            pages += 1
            if not data.get("has_more") or not cursor:
                break
        print(f"[User] Found {len(results)} notes for user {user_id}")
        return results[:max_count]
