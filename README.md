# multi_get_redbook_skill (xhs-scraper)

Self-built Multica skill to scrape Xiaohongshu (小红书 / RED) — note search, author
profile, note details, comments — and write to Feishu bitable. Mirrors the existing
`douyin-scraper` architecture, adapted for Xiaohongshu. **Independent implementation;
it does not reuse the third-party MediaCrawler fork's code** (that project is a
validated reference for the signing *approach* only).

See `SKILL.md` for the full status table, prerequisites, and architecture.

## Quick check (offline, no login)

```bash
pip install -r requirements.txt
python main.py check        # -> "xhs-scraper scaffold OK"
```

## Status

All core features are implemented and working:

- ✅ Scaffold, data models, date filter, storage/downloader
- ✅ Browser response interception (no signature reimplementation needed)
- ✅ Login flow (`python main.py login`) with cookie persistence
- ✅ Scrapers: keyword search, note detail (SSR + DOM fallback), comments + sub-comments, user profile + user search
- ✅ `xsec_token` passthrough across all scraper calls
- ✅ Feishu bitable: auto-create/reuse tables, field sync on existing tables, media upload as attachments
- ✅ Full pipeline (`scrape-all`): search → detail → comments → media → Feishu
- ✅ Login fail-fast (raises immediately if session is missing)

See `SKILL.md` for full command reference and environment variables.

## Login session

XHS requires a logged-in session. Run `python main.py login` to open a browser for QR code
or phone login. Cookies auto-save to `cookies.json` and `.env`. Alternatively, provide the
full cookie string via `XHS_COOKIE` in the agent's custom_env — never via workdir files or
issue comments.
