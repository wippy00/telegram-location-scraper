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
from utils.llm_extractor_gemini import extract_places_from_video



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
            "cookiefile": "/cookies/cookies.txt",  # De-commenta se ti serve
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
            return {"locations": [], "error": None}
            
        reel_url = match.group(1)
        shortcode_match = re.search(r"instagram\.com/reel/([^/?]+)", reel_url)
        shortcode = shortcode_match.group(1) if shortcode_match else "unknown"

        job = None
        video_data = None

        if self.db:
            # Controllo se abbiamo già scaricato con successo questo Reel (sia come message_id che come URL generico)
            existing_job = self.db.get_media_job(self.message_id) if self.message_id else None
            if not existing_job:
                existing_job = self.db.get_media_job_by_source_url(reel_url)
            
            if existing_job and existing_job.download_status == "completed" and existing_job.media_path and os.path.exists(existing_job.media_path):
                print(f"[InstagramExtractor] Reel già elaborato e presente su disco. Skip download.")
                video_data = {
                    "filepath": existing_job.media_path,
                    "description": existing_job.description or "",
                    "metadata": existing_job.raw_metadata or {}
                }
                
                # Se stiamo processando un NUOVO messaggio con lo stesso reel, copiamo un nuovo job
                if self.message_id and existing_job.message_id != self.message_id:
                    job = MediaProcessingJob(
                        message_id=self.message_id,
                        source_url=reel_url,
                        download_status="completed",
                        ocr_status="processing",
                        media_path=existing_job.media_path,
                        description=existing_job.description,
                        raw_metadata=existing_job.raw_metadata
                    )
                    self.db.upsert_media_job(job)
                else:
                    job = existing_job
                    job.ocr_status = "processing"
                    self.db.upsert_media_job(job)
            else:
                if self.message_id:
                    # Inizializza il Job nel DB per il nuovo download
                    job = existing_job or MediaProcessingJob(
                        message_id=self.message_id,
                        source_url=reel_url,
                        download_status="processing"
                    )
                    job.download_status = "processing"
                    self.db.upsert_media_job(job)

        # 3. DOWNLOAD (se non in cache)
        if not video_data:
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
                error_msg = f"Download failed: {str(e)}"
                print(f"[InstagramExtractor] Errore yt-dlp: {error_msg}")
                if job:
                    job.download_status = f"failed: {str(e)}"
                    self.db.upsert_media_job(job)
                return {"locations": [], "error": error_msg}

        # 4-5. GEMINI MULTIMODALE: OCR + LLM EXTRACTION in UNA SOLA CHIAMATA
        # Gemini legge il video (estrae testi, sottotitoli, etc.) + legge la descrizione
        # e restituisce direttamente i posti estratti
        print("[InstagramExtractor] Analizzando video con Google Gemini (OCR + LLM integrato)...")
        
        ai_places = await asyncio.to_thread(
            extract_places_from_video,
            video_data["filepath"],
            video_data["description"]
        )
        
        if job:
            job.ocr_status = "completed"  # Fatto da Gemini internamente
            job.ai_places_json = ai_places
            job.ai_status = "completed" if ai_places else "no_places_found"
            self.db.upsert_media_job(job)

        if not ai_places:
            print("[InstagramExtractor] L'IA non ha trovato nessun luogo valido.")
            return {"locations": [], "error": None}

        # 5. GEOCODING & MERGE DEI DATI
        print(f"[InstagramExtractor] Trovati {len(ai_places)} luoghi dall'IA. Cerco su Maps...")
        final_locations = []

        for ai_place in ai_places:
            # Prendiamo la query suggerita dall'AI
            query_to_search = ai_place.get("google_maps_query") or ai_place.get("name")
            
            # Chiamiamo Google Maps
            if not query_to_search:
                error_msg = f"No valid query for place: {ai_place.get('name')}"
                print(f"[InstagramExtractor] {error_msg}")
                return {"locations": [], "error": error_msg}
            
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

        return {"locations": final_locations, "error": None}