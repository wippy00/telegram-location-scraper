import os
import re
import asyncio
import yt_dlp
from typing import Dict, Any

from .base import BaseExtractor
from pipeline.geocoder import GoogleMapsGeocoder

# Importiamo le tue utility (che abbiamo pulito in precedenza)
from utils.video_ocr import extract_burned_subtitles_text
from utils.llm_extractor import extract_places_via_llm


from models.media_job import MediaProcessingJob
from database.crud import DatabaseCRUD

class InstagramExtractor(BaseExtractor):
    def __init__(self, db: DatabaseCRUD = None, message_id: int = None, download_dir: str = "media/instagram_videos"): # type: ignore
        self.db = db
        self.message_id = message_id
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)
        # Inizializziamo il geocoder qui, esattamente come nel MapsExtractor
        self.geocoder = GoogleMapsGeocoder()

    def _sync_download_reel(self, url: str, shortcode: str) -> dict:
        """Esegue il download del reel con yt-dlp in modo sincrono."""
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "outtmpl": os.path.join(self.download_dir, f"{shortcode}.%(ext)s"),
            "format": "bv*+ba/b",
            "merge_output_format": "mp4",
            "cookiefile": "cookies.txt",  # De-commenta se ti serve
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: # type: ignore
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)
            # Salviamo i metadati completi del video
            raw_metadata = {
                "title": info.get("title"),
                "uploader": info.get("uploader"),
                "uploader_id": info.get("uploader_id"),
                "duration": info.get("duration"),
                "view_count": info.get("view_count"),
                "like_count": info.get("like_count"),
                "comment_count": info.get("comment_count"),
                "timestamp": info.get("timestamp"),
                "tags": info.get("tags", []),
            }
            return {
                "filepath": filepath,
                "description": info.get("description", ""),
                "metadata": raw_metadata
            }

    def _sync_geocoder_resolve(self, query: str) -> dict | None:
        """Wrapper sincrono per il Geocoder."""
        return self.geocoder.resolve(query, download_n_images=3)

    async def process(self, text: str) -> dict:
        """Il metodo chiamato dal router. Esegue l'intera pipeline Instagram."""
        
        # 1. Trova l'URL e lo shortcode
        match = re.search(r"(https?://(?:www\.)?instagram\.com/reel/[^\s]+)", text)
        if not match:
            print("[InstagramExtractor] Nessun link reel trovato nel testo.")
            return {"locations": []}
            
        reel_url = match.group(1)
        shortcode_match = re.search(r"instagram\.com/reel/([^/?]+)", reel_url)
        shortcode = shortcode_match.group(1) if shortcode_match else "unknown"

        job = None
        if self.db and self.message_id:
            # 2. Inizializza il Job nel DB se fornito
            job = MediaProcessingJob(
                message_id=self.message_id,
                source_url=reel_url,
                download_status="processing"
            )
            self.db.upsert_media_job(job)

        # 3. DOWNLOAD (in background)
        try:
            print(f"[InstagramExtractor] Scaricando reel: {shortcode}...")
            video_data = await asyncio.to_thread(self._sync_download_reel, reel_url, shortcode)
            if job:
                job.media_path = video_data["filepath"]
                job.description = video_data["description"]
                job.raw_metadata = video_data["metadata"]
                job.download_status = "completed"
                job.ocr_status = "processing"
                self.db.upsert_media_job(job)
        except Exception as e:
            print(f"[InstagramExtractor] Errore yt-dlp: {e}")
            if job:
                job.download_status = f"failed: {str(e)}"
                self.db.upsert_media_job(job)
            return {"locations": []}

        # 4. OCR (in background)
        print(f"[InstagramExtractor] Eseguendo OCR su {video_data['filepath']}...")
        ocr_text, ocr_status = await asyncio.to_thread(
            extract_burned_subtitles_text, 
            video_data["filepath"]
        )
        if job:
            job.ocr_text = ocr_text
            job.ocr_status = "completed" if ocr_status == "success" else ocr_status
            job.ai_status = "processing"
            self.db.upsert_media_job(job)

        # 5. ESTRAZIONE AI (in background)
        print("[InstagramExtractor] Analizzando con l'LLM...")
        
        ai_places = await asyncio.to_thread(
            extract_places_via_llm, 
            video_data["description"], 
            ocr_text
        )
        
        print(f"[DEBUG] AI places returned: {ai_places}")
        
        if job:
            job.ai_places_json = ai_places
            job.ai_status = "completed" if ai_places else "no_places_found"
            self.db.upsert_media_job(job)

        if not ai_places:
            print("[InstagramExtractor] L'IA non ha trovato nessun luogo valido.")
            return {"locations": []}

        # 5. GEOCODING & MERGE DEI DATI
        print(f"[InstagramExtractor] Trovati {len(ai_places)} luoghi dall'IA. Cerco su Maps...")
        final_locations = []

        for ai_place in ai_places:
            # Prendiamo la query suggerita dall'AI
            query_to_search = ai_place.get("google_maps_query") or ai_place.get("name")
            
            # Chiamiamo Google Maps
            if not query_to_search:
                print(f"[InstagramExtractor] Nessuna query valida per Maps per il luogo: {ai_place.get('name')}")
                return {"locations": []}
            
            maps_data = await asyncio.to_thread(self._sync_geocoder_resolve, query_to_search)

            print("\n\n\n instagram_extractor: " , ai_place.get("description"))
            
            if maps_data:
                loc_data = {
                    "name": maps_data.get("name") or ai_place.get("name"),
                    "lat": maps_data.get("lat"),
                    "lng": maps_data.get("lng"),
                    'description': ai_place.get("description"),  # <--- AI!
                    "address": maps_data.get("address"),
                    "website": maps_data.get("website"),
                    "category": ai_place.get("category"),  # <--- AI!
                    "categories": maps_data.get("categories"),
                    "google_maps_url": maps_data.get("google_maps_url"),
                    "google_place_id": maps_data.get("google_place_id"),
                    "local_photos": maps_data.get("local_photos", [])
                }
                final_locations.append(loc_data)
                print(f"[InstagramExtractor] Validato su Maps: {loc_data['name']}")
            else:
                print(f"[InstagramExtractor] Impossibile trovare su Maps: {query_to_search}")

        return {"locations": final_locations}