---
name: xhs-scraper
description: "Use when the user asks to scrape Xiaohongshu (小红书 / RED) data - keyword search, author profile, note details, comments, user search - and write results to Feishu bitable. Supports media download (images/video) and upload to Feishu attachment fields."
user-invocable: true
---

# Xiaohongshu (小红书) Scraper

Scrape Xiaohongshu data (note search / user search / note detail / comments / author profile) and write to Feishu bitable. Uses browser response interception — no signature reimplementation needed, resilient to XHS algorithm updates.

## Commands

```bash
python main.py check                        # offline smoke test
python main.py login                        # QR code login (saves cookies)
python main.py search <keyword> -n 20       # note keyword search
python main.py search-user <keyword> -n 20  # user search
python main.py note <id> <xsec_token>       # note detail
python main.py comment <id> <xsec_token>    # note comments
python main.py user <id> [--notes]          # author profile + notes
python main.py scrape-all -k <keyword>      # full pipeline → Feishu
```

## Full Pipeline (`scrape-all`)

Runs all steps in sequence:
1. **Search** — keyword search, get note list with `xsec_token`
2. **Detail** — SSR extraction from `__INITIAL_STATE__` + DOM fallback for interaction data
3. **Comments** — browser interception + cursor paging (with parent/reply tracking)
4. **Media** — download images/video, upload to Feishu as attachments
5. **Write** — batch write notes + comments to Feishu bitable

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `XHS_KEYWORD` | for `scrape-all` | Default search keyword |
| `MAX_NOTES` | no (default 20) | Max notes to fetch |
| `MAX_COMMENTS_PER_NOTE` | no (default 50) | Max first-level comments per note |
| `MAX_SUB_COMMENTS_PER` | no (default 20) | Max sub-comments (replies) per first-level comment |
| `SKIP_DETAIL` | no | Set `true` to skip note detail step |
| `SKIP_COMMENTS` | no | Set `true` to skip comments step (also skips comment table creation) |
| `SKIP_MEDIA` | no | Set `true` to skip media download/upload |
| `FEISHU_APP_ID` | for Feishu | Feishu app ID |
| `FEISHU_APP_SECRET` | for Feishu | Feishu app secret |
| `FEISHU_APP_TOKEN` | for Feishu | Feishu bitable app token |
| `NOTE_TABLE_ID` | no | Note table ID (auto-created if empty, reuses existing by name) |
| `COMMENT_TABLE_ID` | no | Comment table ID (auto-created if empty, reuses existing by name) |
| `REQUEST_DELAY` | no (default 3) | Seconds between requests |

## Login

XHS requires a logged-in session. Run `python main.py login` — a browser window opens for QR code or phone login. Cookies auto-save to `cookies.json` and `.env`.

If the session expires during scraping, the auto-login flow (`ensure_login`) opens a browser window for re-authentication.

**Never paste cookies in issue comments.** Use `.env` or Multica agent `custom_env`.

## Architecture

```
config/settings.py      env + endpoints
core/browser.py         Playwright context + auto-login + in-page fetch
core/datefilter.py      client-side date-window filter
models/data.py          NoteInfo / XhsUserInfo / CommentInfo (with parent/reply fields)
scrapers/keyword.py     note search (response interception)
scrapers/note.py        note detail (SSR + API fallback + DOM enrichment)
scrapers/comment.py     comments (interception + cursor API + sub-comments)
scrapers/user.py        user profile + user search + user notes
storage/feishu.py       Feishu bitable writer + file upload + auto-create/reuse tables
storage/downloader.py   media download
scrape_all.py           full pipeline orchestrator
```

## Key Design Notes

- **Browser response interception** — captures XHS's own signed API responses; no signature reimplementation. More stable than pure algorithm signing (e.g. MediaCrawler's xhshow approach).
- **`xsec_token` passthrough** — every note carries a per-note `xsec_token` from search results; it must be passed to detail/comment requests.
- **SSR + DOM fallback** — note detail extracts from `window.__INITIAL_STATE__`; when interaction counts are missing, falls back to DOM scraping.
- **Auto-create / reuse tables** — if `NOTE_TABLE_ID` or `COMMENT_TABLE_ID` are not set, automatically finds an existing table by name or creates a new one with the correct schema. Set table IDs to reuse specific existing tables.
- **Comment threading** — `CommentInfo` carries `parent_comment_id`, `reply_to_nickname`, and `reply_to_user_id` to track reply relationships in both first-level and sub-comments.
- **Media pipeline** — downloads cover/images/video, uploads to Feishu via Drive API, writes file_tokens as attachment fields (type 17).
