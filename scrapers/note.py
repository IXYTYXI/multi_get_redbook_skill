"""Note detail — extract from page's __INITIAL_STATE__ or API interception.

XHS now server-side renders note detail into ``__INITIAL_STATE__`` (no
``/feed`` API call). We read it via ``page.evaluate()`` after navigating.
Falls back to ``/api/sns/web/v1/feed`` interception for older page versions.
"""
import asyncio
import time
from typing import Optional

from models.data import NoteInfo
from scrapers.keyword import _to_int

FEED_API = "/api/sns/web/v1/feed"

_EXTRACT_JS = """(noteId) => {
    const s = window.__INITIAL_STATE__;
    if (!s || !s.note || !s.note.noteDetailMap) return null;
    const entry = s.note.noteDetailMap[noteId];
    if (!entry || !entry.note) return null;
    return JSON.parse(JSON.stringify(entry.note));
}"""


class NoteScraper:
    def __init__(self, browser):
        self.browser = browser

    async def get_note(
        self,
        note_id: str,
        xsec_token: str,
        xsec_source: str = "pc_search",
    ) -> Optional[NoteInfo]:
        captured = []

        async def on_response(resp):
            if FEED_API in resp.url:
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

        # Primary: extract from __INITIAL_STATE__ (SSR)
        try:
            nc = await self.browser.page.evaluate(_EXTRACT_JS, note_id)
            if nc and isinstance(nc, dict):
                return self._parse(nc, note_id, xsec_token, xsec_source)
        except Exception:
            pass

        # Fallback: intercept /feed API response
        for r in captured:
            if not isinstance(r, dict):
                continue
            items = (r.get("data") or {}).get("items", [])
            for it in items:
                nc = it.get("note_card")
                if not nc:
                    continue
                return self._parse(nc, note_id, xsec_token, xsec_source)

        return None

    def _parse(
        self, nc: dict, note_id: str, xsec_token: str, xsec_source: str
    ) -> NoteInfo:
        user = nc.get("user", {}) or {}
        interact = nc.get("interact_info", {}) or {}

        # Images
        image_list = nc.get("image_list") or []
        image_urls = []
        for img in image_list:
            info_list = img.get("info_list") or []
            url = img.get("url_default") or img.get("url_pre") or ""
            if not url and info_list:
                url = info_list[-1].get("url", "")
            if url:
                image_urls.append(url)

        # Video
        video = nc.get("video") or {}
        video_url = ""
        media = video.get("media") or {}
        stream = media.get("stream") or {}
        h264 = stream.get("h264") or []
        if h264:
            video_url = h264[0].get("master_url", "")
        if not video_url:
            consumer = video.get("consumer") or {}
            origin = consumer.get("origin_video_key", "")
            if origin:
                video_url = f"https://sns-video-bd.xhscdn.com/{origin}"

        # Cover
        cover = nc.get("cover", {}) or {}
        cover_url = cover.get("url_default") or cover.get("url_pre") or ""
        if not cover_url and image_urls:
            cover_url = image_urls[0]

        # Tags
        tag_list = nc.get("tag_list") or []
        tags = ", ".join(t.get("name", "") for t in tag_list if t.get("name"))

        # Create time
        ct = nc.get("time") or nc.get("create_time") or 0
        if isinstance(ct, (int, float)) and ct > 1000000000:
            create_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ct / 1000 if ct > 10000000000 else ct))
        else:
            create_time = str(ct) if ct else ""

        return NoteInfo(
            note_id=note_id,
            xsec_token=xsec_token,
            xsec_source=xsec_source,
            note_type=nc.get("type", ""),
            title=nc.get("title") or nc.get("display_title", ""),
            desc=nc.get("desc", ""),
            author_nickname=user.get("nick_name") or user.get("nickname", ""),
            author_user_id=user.get("user_id", ""),
            liked_count=_to_int(interact.get("liked_count")),
            collected_count=_to_int(interact.get("collected_count")),
            comment_count=_to_int(interact.get("comment_count")),
            share_count=_to_int(interact.get("shared_count")),
            create_time=create_time,
            cover_url=cover_url,
            video_url=video_url,
            image_urls=", ".join(image_urls),
            note_url=(
                f"https://www.xiaohongshu.com/explore/{note_id}"
                f"?xsec_token={xsec_token}&xsec_source={xsec_source}"
            ),
            tags=tags,
        )
