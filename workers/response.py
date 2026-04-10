import os
import json
from dotenv import load_dotenv
load_dotenv()
from data.database import Database

db = Database("sqlite:///data/database.db")

def send_telegram_reply(reply_msg_id: int, text: str):
    from telethon.sync import TelegramClient
    import logging
    
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    
    out_chat = os.getenv("TELEGRAM_OUTPUT_CHAT_ID", os.getenv("TELEGRAM_CHAT_ID"))
    if not api_id or not api_hash or not out_chat:
        print("[Telegram Reply] Missing credentials for Telegram reply.")
        return
        
    chat_id = int(out_chat)
    
    try:
        logging.getLogger('telethon').setLevel(logging.WARNING)
        with TelegramClient('telegram_session', int(api_id), api_hash) as client:
            client.send_message(entity=chat_id, message=text, reply_to=reply_msg_id)
            print(f"[Telegram Reply] Replied to msg {reply_msg_id} in {chat_id}")
    except Exception as e:
        print(f"[Telegram Reply] API Error: {e}")


if __name__ == "__main__":
    reels = db.get_reels_by_pipeline_status("pending_response")
    
    for reel in reels:
        print(f"[Response Worker] Processing reel: {reel.shortcode}")
        
        place_count = len(reel.ai_places_json) if reel.ai_places_json else 0
        
        if place_count > 0:
            links_parts = []
            for i, place in enumerate(reel.ai_places_json, start=1):
                if "google_maps_url" in place and place["google_maps_url"]:
                    links_parts.append(f"{i}. [{place['name']}] - {place['google_maps_url']}")
            
            links_text = "\\n".join(links_parts)
            json_formatted = json.dumps(reel.ai_places_json, indent=2, ensure_ascii=False)
            reply_message = f"🔗 **Analisi Reel:** {reel.source_url}\\n\\n```json\\n{json_formatted}\\n```\\n\\n📌 **Maps Link:**\\n{links_text}\\n\\n#ignore"
            
            send_telegram_reply(reply_msg_id=reel.telegram_id, text=reply_message)
        else:
            send_telegram_reply(reply_msg_id=reel.telegram_id, text=f"🔗 **Analisi Reel:** {reel.source_url}\\n\\nNessun luogo rilevato o non ho trovato match concreti per la query su Google Maps.\\n\\n#ignore")
             
        if db.has_location_for_source_url(reel.source_url):
            reel.pipeline_status = "done"
            db.update_message_status(reel.telegram_id, "done", category="instagram")
            print("[Response Worker] Telegram message status updated to done.")
        else:
            reel.pipeline_status = "processed"
            db.update_message_status(reel.telegram_id, "processed", category="instagram")
            print("[Response Worker] No location saved for this reel, status remains processed.")
             
        db.upsert_instagram_reel(reel)

        print("[Response Worker] Message sent. Pipeline completed.")
