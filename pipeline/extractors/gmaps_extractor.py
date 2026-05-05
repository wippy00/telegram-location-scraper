import re
import asyncio
import requests
from pipeline.geocoder import GoogleMapsGeocoder
from .base import BaseExtractor

class MapsExtractor(BaseExtractor):
    def __init__(self):

        self.geocoder = GoogleMapsGeocoder()

    def _extract_url_from_text(self, text: str) -> str | None:
        """Trova il link di Google Maps nascosto in mezzo alle parole del messaggio."""
        match = re.search(r'(https?://(?:www\.)?(?:maps\.app\.goo\.gl|goo\.gl/maps|maps\.google\.com|google\.com/maps)[^\s]+)', text)
        return match.group(1) if match else None

    def _sync_resolve_short_url(self, url: str) -> str:
        """Se è un link corto, ottiene quello lungo."""
        if "maps.app.goo.gl" in url or "goo.gl" in url:
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.head(url, allow_redirects=True, headers=headers, timeout=5)
                return response.url
            except:
                return url
        return url

    def _sync_geocoder_resolve(self, url: str) -> dict | None:
        """Funzione wrapper sincrona per chiamare il geocoder"""
        return self.geocoder.resolve(url, download_n_images=5)

    def _extract_text_before_url(self, text: str) -> str | None:
        """Estrae il testo prima del link, se presente."""
        url = self._extract_url_from_text(text)
        if not url:
            return None
        idx = text.find(url)
        if idx > 0:
            extracted = text[:idx].strip()
            if extracted:
                return extracted
        return None

    def _extract_fallback_query(self, long_url: str) -> str | None:
        """Estrae una query sensata dall'URL per il fallback."""
        # Usa il metodo del geocoder per pulire l'URL
        cleaned = self.geocoder._clean_query(long_url)
        # Se è ancora un URL, significa che non siamo riusciti a estrarre nulla
        if cleaned.startswith("http"):
            return None
        return cleaned

    async def process(self, text: str) -> dict:
        """Il metodo chiamato dal router.py"""
        
        url = self._extract_url_from_text(text)
        
        if not url:
            return {"locations": []}

        # Eseguiamo la risoluzione dell'URL in un thread separato per non bloccare il bot
        long_url = await asyncio.to_thread(self._sync_resolve_short_url, url)

        # Chiamiamo il geocoder internamente (come avevi scritto tu)
        geocoder_result = await asyncio.to_thread(self._sync_geocoder_resolve, long_url)
        
        if geocoder_result:
            return {"locations": [geocoder_result]}
        
        # FALLBACK 1: Se il messaggio ha testo prima del link, usalo
        fallback_text = self._extract_text_before_url(text)
        if fallback_text:
            fallback_result = await asyncio.to_thread(self.geocoder.search_by_text, fallback_text, 5)
            if fallback_result:
                return {"locations": [fallback_result]}
        
        # FALLBACK 2: Estrai il testo dal path dell'URL
        fallback_query = self._extract_fallback_query(long_url)
        if fallback_query:
            fallback_result = await asyncio.to_thread(self.geocoder.search_by_text, fallback_query, 5)
            if fallback_result:
                return {"locations": [fallback_result]}
            
        return {"locations": []}