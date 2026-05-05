import asyncio
from pipeline.geocoder import GoogleMapsGeocoder
from .base import BaseExtractor
from utils.category_infer import infer_location_category

class AddressExtractor(BaseExtractor):
    def __init__(self):
        self.geocoder = GoogleMapsGeocoder()

    def _sync_search_place(self, query: str) -> dict | None:
        """Funzione wrapper sincrona per chiamare il geocoder"""
        return self.geocoder.resolve(query)

    async def process(self, text: str) -> dict:
        """Il metodo chiamato dal router.py"""
        
        query = (text or "").strip()
        if not query:
            return {"locations": []}

        # Chiamiamo il geocoder internamente
        geocoder_result = await asyncio.to_thread(self._sync_search_place, query)
        
        if geocoder_result:
            # Aggiungiamo la categoria inferita
            geocoder_result['category'] = infer_location_category(query)
            return {"locations": [geocoder_result]}
            
        return {"locations": []}
