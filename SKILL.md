---
name: xhs-scraper
description: "Use when the user asks to scrape Xiaohongshu (小红书 / RED) data - note keyword search, author profile, note details, or comments - and write results to Feishu bitable. WIP: scaffold + reused storage/date-filter are done; signing core (Stage 1) and scrapers (Stage 2) are login-gated stubs."
user-invocable: true
---

# Xiaohongshu (小红书) Scraper — WIP

Self-built skill to scrape Xiaohongshu data (note search / author profile / note detail / comments) and write to Feishu bitable. Independent implementation — **does not** reuse the third-party MediaCrawler fork's code.

## Status

| Stage | Scope | State |
|---|---|---|
| 0 | Scaffold, reused storage / downloader / date-filter, data models | ✅ done |
| 1 | Browser-injection signing (`x-s`/`x-t`/`x-s-common`) | ✅ implemented — needs live validation with a logged-in cookie |
| 2 | Scrapers: search / note / comment / user (with `xsec_token` passthrough) | ✅ implemented (parsers offline-tested) |
| 3 | Signed client, Feishu / local output, per-command orchestration | ✅ implemented |
| 4 | Docs, `.env.example`, known limits | ✅ this file + README |

> **Live-validation caveat (Stage 1):** `x-s` / `x-t` come straight from the
> page's own signer, so they track XHS updates automatically. The `x-s-common`
> envelope (version strings + the `x9` checksum) is assembled in Python and can
> only be confirmed against a real logged-in session — which needs a user cookie.
> If XHS returns risk-control `300012` / `300015`, the client raises a labelled
> `XhsResponseError` so the envelope constants in `core/sign.py` can be tuned.

## Prerequisites

### 1. Xiaohongshu login session (Stage 1+)

Signing requires a logged-in browser session. Two ways to provide it (same as
douyin-scraper):

**A. `login` command (recommended on a desktop runtime).** Run:

```bash
python main.py login
```

A visible browser opens; log into `xiaohongshu.com` (QR or phone). Once login is
detected it auto-saves the session to **`cookies.json`** (a Playwright cookie array)
in the skill root and mirrors the cookie string to `.env` as `XHS_COOKIE`. Scraping
then loads `cookies.json` automatically. `cookies.json` / `.env` are git-ignored.

**B. `XHS_COOKIE` env var.** If you already have the full cookie string (key fields
`a1`, `web_session`), set it as `XHS_COOKIE` (e.g. the agent's custom_env). Used only
when no `cookies.json` is present.

- **Never paste the cookie in issue comments.** Use a throwaway account.

### 2. Feishu app credentials

`.env` (or env) needs `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_APP_TOKEN` and the
target table ids. See `.env.example`.

### 3. Playwright

`pip install -r requirements.txt && playwright install chromium`

## Architecture (mirrors douyin-scraper, adapted for XHS)

```
config/settings.py     env + endpoints
core/sign.py           x-s / x-t / x-s-common (browser-injection; Stage 1)
core/browser.py        Playwright logged-in context + in-page fetch
core/datefilter.py     client-side date-window filter (reused)
models/data.py         NoteInfo / XhsUserInfo / CommentInfo
scrapers/keyword.py    note search (extracts xsec_token)  [stub]
scrapers/note.py       note detail (token passthrough)    [stub]
scrapers/comment.py    comments (cursor paging)           [stub]
scrapers/user.py       author profile                     [stub]
storage/feishu.py      Feishu bitable writer (reused)
storage/downloader.py  media download (reused)
```

## Key design notes (vs douyin-scraper)

- **Signing is mandatory on all endpoints** — no cookie-only fast path. We compute the
  obfuscated core value inside a logged-in page (`page.evaluate`) and assemble the header
  envelope in Python. Independent implementation; the fork is a validated reference only.
- **`xsec_token` passthrough** — list/search responses carry a per-note `xsec_token`
  (+ `xsec_source`); it must be threaded into note-detail and comment requests. A bare
  `note_id` cannot be resolved (risk-control error 300017).

## Commands

```bash
python main.py check                       # offline smoke test (no login)
python main.py login                       # QR login -> cookies.json + .env
python main.py search "护肤" -n 30          # keyword note search -> Feishu/local
python main.py search "护肤" --detail --comments   # + full detail + comments
python main.py note   <note_id> <xsec_token>       # single note detail
python main.py comment <note_id> <xsec_token> -n 100
python main.py user   <user_id> --xsec-token <t>   # profile + notes
```

Output goes to Feishu when `FEISHU_APP_ID` + the matching `*_TABLE_ID` are set;
otherwise (or with `--local`) it lands in `output/*.json` + `*.csv`. `xsec_token`
from search/list is threaded automatically into detail/comment calls.

## Smoke test

```bash
python main.py check
```
Runs offline: builds the models, exercises the date filter, runs every Stage-2
parser against API-shaped fixtures, and imports every module. No network/login.
