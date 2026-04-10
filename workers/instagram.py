import os
import yt_dlp
import time
import random
import json
import re
from typing import Any, Mapping, cast
from dotenv import load_dotenv
load_dotenv()

from data.database import Database
from models.instagram_reel import InstagramReel

db = Database("sqlite:///data/database.db")

def extract_instagram_reel_url(text: str) -> str | None:
    pattern = r"(https?://(?:www\.)?instagram\.com/reel/[^\s]+)"
    match = re.search(pattern, text)
    return match.group(1) if match else None

def extract_reel_id(text: str) -> str | None:
    pattern = r"instagram\.com/reel/([^/?]+)"
    match = re.search(pattern, text)
    return match.group(1) if match else None

def _clean_yt_dlp_info(info: Mapping[str, Any]) -> dict[str, Any]:
    cleaned_info: dict[str, Any] = {}
    for key, value in info.items():
        if key in ["_postprocessors", "postprocessors", "progress_hooks"]:
            continue
        try:
            json.dumps(value)
            cleaned_info[key] = value
        except (TypeError, OverflowError):
            print(f"[Cleaner] Skipping non-serializable key: {key}")
            continue
    return cleaned_info

if __name__ == "__main__":
    messages = db.get_messages_by_category("instagram")

    for message in messages:

        existing_reel = db.get_instagram_reel_by_telegram_id(message.telegram_id)
        
        
        if existing_reel:
            print("[Instagram] Reel already exists, skipping download phase.")
            db.update_message_status(message.telegram_id, "processed", category="instagram")
            continue

        print("[Instagram] Processing message for reel:", message.raw_text[:50])
        
        reel_url = extract_instagram_reel_url(message.raw_text)
        if not reel_url:
            print("[Instagram] No reel URL found, skipping.")
            continue

        shortcode = extract_reel_id(reel_url)
        if not shortcode:
            print("[Instagram] Could not extract shortcode, skipping.")
            continue

        expected_video_path = os.path.join("data", "instagram_videos", f"{shortcode}.mp4")
        if os.path.exists(expected_video_path):
            print(f"[Instagram] Video already exists at: {expected_video_path}")
            continue

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "outtmpl": os.path.join("data", "instagram_videos", f"{shortcode}.%(ext)s"),
            "format": "bv*+ba/b",
            "merge_output_format": "mp4",
            "cookiefile": "cookies.txt",
        }

        info = None
        filepath = None
        download_status = "unknown"

        try:
            with yt_dlp.YoutubeDL(cast(Any, ydl_opts)) as ydl:
                info = ydl.extract_info(reel_url, download=True)
                filepath = ydl.prepare_filename(info)
                download_status = "downloaded"
                print(f"[Instagram] Downloaded reel to: {filepath}")
        except Exception as e:
            download_status = "failed"
            print(f"[Instagram] ERROR: Download failed for {reel_url}. Reason: {e}")
            continue

        if not info:
            print("[Instagram] No info extracted, cannot save to DB.")
            continue

        reel = InstagramReel(
            telegram_id=message.telegram_id,
            source_url=reel_url,
            shortcode=shortcode,
            extraction_method="yt_dlp",
            name=info.get("title"),
            description=info.get("description"),
            uploader=info.get("uploader"),
            video_path=filepath,
            video_download_status=download_status,
            ocr_text=None,
            ocr_status="skipped_no_video_path" if not filepath else "unknown",
            audio_transcript=None,
            asr_status="disabled",
            ai_source="none",
            ai_status="disabled",
            ai_places_json=None,
            raw_payload=_clean_yt_dlp_info(info),
            pipeline_status="pending_ocr",
        )
        
        db.upsert_instagram_reel(reel) 
        db.update_message_status(message.telegram_id, "processed", category="instagram")
        print("[Instagram] Reel object saved to DB. Moving to pending_ocr.")

        sleep_time = random.uniform(25, 36)
        time.sleep(sleep_time)
        print(f"[Instagram] Waiting for {sleep_time:.2f} seconds")
