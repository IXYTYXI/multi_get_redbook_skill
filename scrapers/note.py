"""Note detail.

Endpoint: ``POST /api/sns/web/v1/feed``. Requires ``source_note_id`` +
``xsec_token`` (+ ``xsec_source``); a bare note_id triggers risk-control 300017.
"""
import time
from typing import Optional

from config.settings import XHS_BASE_URL
from models.data import NoteInfo
from scrapers.keyword import to_int

FEED_URI = "/api/sns/web/v1/feed"


def _fmt_time(ms) -> str:
    try:
        ts = int(ms)
    except (TypeError, ValueError):
        return ""
    if ts <= 0:
        return ""
    # XHS timestamps are milliseconds.
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts / 1000))


def parse_note_card(note_id: str, card: dict, xsec_token: str, xsec_source: str) -> NoteInfo:
    """Parse a feed ``note_card`` (full detail) into NoteInfo."""
    user = card.get("user") or {}
    interact = card.get("interact_info") or {}

    image_urls = []
    for img in card.get("image_list", []) or []:
        info = (img.get("info_list") or [{}])
        url = ""
        for it in info:
            if it.get("image_scene") in ("WB_DFT", "CRD_PRV_WEBP") or it.get("url"):
                url = it.get("url", "")
                if url:
                    break
        url = url or img.get("url", "")
        if url:
            image_urls.append(url)

    video_url = ""
    video = card.get("video") or {}
    if video:
        streams = ((video.get("media") or {}).get("stream") or {})
        for codec in ("h264", "h265", "av1"):
            arr = streams.get(codec) or []
            if arr:
                video_url = arr[0].get("master_url") or arr[0].get("backup_urls", [""])[0]
                if video_url:
                    break

    tags = [t.get("name", "") for t in card.get("tag_list", []) or [] if t.get("name")]
    cover = card.get("cover") or {}
    cover_url = cover.get("url_default") or cover.get("url") or (image_urls[0] if image_urls else "")

    note_url = f"{XHS_BASE_URL}/explore/{note_id}"
    if xsec_token:
        note_url += f"?xsec_token={xsec_token}&xsec_source={xsec_source}"

    return NoteInfo(
        note_id=note_id,
        xsec_token=xsec_token,
        xsec_source=xsec_source,
        note_type=card.get("type", ""),
        title=card.get("title", ""),
        desc=card.get("desc", ""),
        author_nickname=user.get("nickname") or user.get("nick_name") or "",
        author_user_id=user.get("user_id", ""),
        liked_count=to_int(interact.get("liked_count")),
        collected_count=to_int(interact.get("collected_count")),
        comment_count=to_int(interact.get("comment_count")),
        share_count=to_int(interact.get("share_count")),
        create_time=_fmt_time(card.get("time") or card.get("last_update_time")),
        cover_url=cover_url,
        video_url=video_url,
        image_urls=",".join(image_urls),
        note_url=note_url,
        tags=",".join(tags),
    )


class NoteScraper:
    def __init__(self, client=None):
        self.client = client

    async def get_note(
        self, note_id: str, xsec_token: str, xsec_source: str = "pc_search"
    ) -> Optional[NoteInfo]:
        payload = {
            "source_note_id": note_id,
            "image_formats": ["jpg", "webp", "avif"],
            "extra": {"need_body_topic": "1"},
            "xsec_source": xsec_source or "pc_search",
            "xsec_token": xsec_token,
        }
        data = await self.client.post(FEED_URI, payload)
        items = data.get("items", []) or []
        if not items:
            print(f"[Note] no detail returned for {note_id}")
            return None
        card = items[0].get("note_card") or {}
        return parse_note_card(note_id, card, xsec_token, xsec_source or "pc_search")
