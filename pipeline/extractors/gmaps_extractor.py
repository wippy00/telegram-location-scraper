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
            
        return {"locations": []}