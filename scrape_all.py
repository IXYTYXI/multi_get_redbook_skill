"""Full pipeline: search notes → get detail → get comments → write to Feishu.

Usage:
  python scrape_all.py                        # uses XHS_KEYWORD from .env
  python scrape_all.py --keyword "美食" -n 20  # override keyword and count
"""
import sys
sys.stdout.reconfigure(errors="replace")

import asyncio
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import REQUEST_DELAY, XHS_KEYWORD
from core.browser import XhsBrowser
from scrapers.keyword import KeywordScraper
from scrapers.note import NoteScraper
from scrapers.comment import CommentScraper
from storage.feishu import (
    FeishuBitable,
    note_to_feishu_record,
    comment_to_feishu_record,
)
from storage.downloader import download_note_media, cleanup_downloads

NOTE_TABLE_ID = os.environ.get("NOTE_TABLE_ID", "")
COMMENT_TABLE_ID = os.environ.get("COMMENT_TABLE_ID", "")
APP_TOKEN = os.environ.get("FEISHU_APP_TOKEN", "")
KEYWORD = os.environ.get("XHS_KEYWORD", "")
MAX_NOTES = int(os.environ.get("MAX_NOTES", "20"))
MAX_COMMENTS_PER_NOTE = int(os.environ.get("MAX_COMMENTS_PER_NOTE", "50"))
SKIP_COMMENTS = os.environ.get("SKIP_COMMENTS", "").lower() in ("1", "true", "yes")
SKIP_DETAIL = os.environ.get("SKIP_DETAIL", "").lower() in ("1", "true", "yes")
SKIP_MEDIA = os.environ.get("SKIP_MEDIA", "").lower() in ("1", "true", "yes")


async def main(keyword: str = "", max_notes: int = 0):
    kw = keyword or KEYWORD
    if not kw:
        print("ERROR: No keyword. Set XHS_KEYWORD in .env or pass --keyword.")
        return

    n = max_notes or MAX_NOTES
    print(f"=== Step 1: Search notes for '{kw}' (max {n}) ===")

    async with XhsBrowser() as browser:
        # Step 1: Search
        ks = KeywordScraper(browser)
        notes = await ks.search_notes(kw, max_count=n)
        print(f"  Found {len(notes)} notes")
        if not notes:
            print("No notes found!")
            return

        # Step 2: Get detail for each note (fills desc, images, video, tags)
        if not SKIP_DETAIL:
            print(f"\n=== Step 2: Get detail for {len(notes)} notes ===")
            ns = NoteScraper(browser)
            detailed = []
            for i, note in enumerate(notes):
                if not note.xsec_token:
                    print(f"  [{i+1}/{len(notes)}] {note.note_id} — skip (no token)")
                    detailed.append(note)
                    continue
                print(f"  [{i+1}/{len(notes)}] {note.note_id} '{note.title[:30]}'")
                detail = await ns.get_note(note.note_id, note.xsec_token, note.xsec_source)
                if detail:
                    detailed.append(detail)
                    img_count = len(detail.image_urls.split(",")) if detail.image_urls else 0
                    print(f"    → desc={len(detail.desc)}c images={img_count} video={'yes' if detail.video_url else 'no'} tags={detail.tags[:40]}")
                else:
                    detailed.append(note)
                    print(f"    → detail failed, using search data")
                await asyncio.sleep(REQUEST_DELAY)
            notes = detailed
        else:
            print("\n=== Step 2: Skipped (SKIP_DETAIL set) ===")

        # Step 3: Get comments
        all_comments = []
        if not SKIP_COMMENTS:
            print(f"\n=== Step 3: Get comments for {len(notes)} notes ===")
            cs = CommentScraper(browser)
            for i, note in enumerate(notes):
                if note.comment_count == 0:
                    print(f"  [{i+1}/{len(notes)}] {note.note_id} — skip (0 comments)")
                    continue
                if not note.xsec_token:
                    print(f"  [{i+1}/{len(notes)}] {note.note_id} — skip (no token)")
                    continue
                print(f"  [{i+1}/{len(notes)}] {note.note_id} (comments: {note.comment_count})")
                comments = await cs.get_comments(
                    note.note_id, note.xsec_token,
                    max_count=MAX_COMMENTS_PER_NOTE,
                    xsec_source=note.xsec_source,
                )
                all_comments.extend(comments)
                print(f"    → got {len(comments)} comments")
                await asyncio.sleep(REQUEST_DELAY)
            print(f"  Total comments: {len(all_comments)}")
        else:
            print("\n=== Step 3: Skipped (SKIP_COMMENTS set) ===")

    # Step 4: Download media + upload to Feishu
    print(f"\n=== Step 4: Write to Feishu ===")
    if not APP_TOKEN:
        print("  FEISHU_APP_TOKEN not set — writing to local summary instead.")
        _print_summary(notes, all_comments)
        return

    feishu = FeishuBitable(app_token=APP_TOKEN)

    # Download and upload media if not skipped
    note_media_tokens = {}
    if not SKIP_MEDIA and NOTE_TABLE_ID:
        print(f"\n  --- Downloading & uploading media for {len(notes)} notes ---")
        for i, note in enumerate(notes):
            has_media = note.image_urls or note.video_url or note.cover_url
            if not has_media:
                continue
            print(f"  [{i+1}/{len(notes)}] {note.note_id} downloading media...")
            paths = download_note_media(note)
            tokens = {"cover": "", "video": "", "images": []}
            if paths["cover"]:
                ft = feishu.upload_file(paths["cover"])
                if ft:
                    tokens["cover"] = ft
                    print(f"    → cover uploaded")
            if paths["video"]:
                ft = feishu.upload_file(paths["video"])
                if ft:
                    tokens["video"] = ft
                    print(f"    → video uploaded")
            for img_path in paths.get("images", []):
                ft = feishu.upload_file(img_path)
                if ft:
                    tokens["images"].append(ft)
            if tokens["images"]:
                print(f"    → {len(tokens['images'])} images uploaded")
            note_media_tokens[note.note_id] = tokens
        cleanup_downloads()
        print(f"  Media done: {len(note_media_tokens)} notes with media")
    elif SKIP_MEDIA:
        print("  Media download skipped (SKIP_MEDIA set)")

    if NOTE_TABLE_ID:
        note_records = [note_to_feishu_record(n) for n in notes]
        for j, r in enumerate(note_records):
            r["搜索关键词"] = kw
            r["爬取时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            mt = note_media_tokens.get(notes[j].note_id, {})
            if mt.get("cover"):
                r["封面附件"] = [{"file_token": mt["cover"]}]
            if mt.get("video"):
                r["视频附件"] = [{"file_token": mt["video"]}]
            if mt.get("images"):
                r["图片附件"] = [{"file_token": ft} for ft in mt["images"]]
        written = feishu.write_records(note_records, NOTE_TABLE_ID)
        print(f"  Written {written}/{len(note_records)} note records")
    else:
        print("  NOTE_TABLE_ID not set, skipping note write")

    if COMMENT_TABLE_ID and all_comments:
        comment_records = [comment_to_feishu_record(c) for c in all_comments]
        for r in comment_records:
            r["搜索关键词"] = kw
            r["爬取时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        written = feishu.write_records(comment_records, COMMENT_TABLE_ID)
        print(f"  Written {written}/{len(comment_records)} comment records")
    elif all_comments:
        print("  COMMENT_TABLE_ID not set, skipping comment write")

    feishu.close()

    print(f"\n=== Done ===")
    print(f"  Notes: {len(notes)}, Comments: {len(all_comments)}")


def _print_summary(notes, comments):
    print(f"\n--- Notes ({len(notes)}) ---")
    for i, n in enumerate(notes, 1):
        print(f"{i:>2}. [{n.note_type}] {n.title[:40]}")
        print(f"    by {n.author_nickname} | 赞{n.liked_count} 藏{n.collected_count} 评{n.comment_count}")
        if n.desc:
            print(f"    desc: {n.desc[:60]}...")
    if comments:
        print(f"\n--- Comments ({len(comments)}) ---")
        for i, c in enumerate(comments[:20], 1):
            print(f"{i:>2}. [{c.user_nickname}] {c.content[:50]}")
        if len(comments) > 20:
            print(f"    ... and {len(comments) - 20} more")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", "-k", default="")
    parser.add_argument("--max-notes", "-n", type=int, default=0)
    args = parser.parse_args()
    asyncio.run(main(args.keyword, args.max_notes))
