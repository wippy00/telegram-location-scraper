import os
import re
import requests
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Any, List

from models.location import MarkerCategory


class GoogleMapsGeocoder:
    def __init__(self, media_folder: str = "media/places"):
        self.api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        self.text_search_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
        self.details_url = "https://maps.googleapis.com/maps/api/place/details/json"
        self.photo_url = "https://maps.googleapis.com/maps/api/place/photo"
        
        # Cartella dove salveremo le immagini
        self.media_folder = media_folder
        os.makedirs(self.media_folder, exist_ok=True)

    def _map_google_types_to_category(self, gmaps_types: List[str]) -> Optional[MarkerCategory]:
        """
        Mappa i 'types' di Google Maps alla nostra MarkerCategory.
        La logica è basata su priorità: se trovo una categoria 'forte', la uso subito.
        """
        if not gmaps_types:
            return None

        # Mappe di priorità da type di Google a MarkerCategory
        # (dalla più specifica alla più generica)
        mapping = {
            # CIBO
            "restaurant": MarkerCategory.FOOD,
            "cafe": MarkerCategory.FOOD,
            "bar": MarkerCategory.FOOD,
            "bakery": MarkerCategory.FOOD,
            "meal_takeaway": MarkerCategory.FOOD,
            "meal_delivery": MarkerCategory.FOOD,

            # CULTURA E SVAGO
            "museum": MarkerCategory.CULTURE,
            "art_gallery": MarkerCategory.CULTURE,
            "tourist_attraction": MarkerCategory.LANDMARK,
            "park": MarkerCategory.FUN,
            "amusement_park": MarkerCategory.FUN,
            "zoo": MarkerCategory.FUN,
            "aquarium": MarkerCategory.FUN,
            "landmark": MarkerCategory.LANDMARK,
            "church": MarkerCategory.CULTURE,
            "hindu_temple": MarkerCategory.CULTURE,
            "mosque": MarkerCategory.CULTURE,
            "synagogue": MarkerCategory.CULTURE,
            "place_of_worship": MarkerCategory.CULTURE,
            "library": MarkerCategory.CULTURE,
            "movie_theater": MarkerCategory.FUN,
            "stadium": MarkerCategory.FUN,

            # TRASPORTI
            "airport": MarkerCategory.TRANSPORT,
            "train_station": MarkerCategory.TRANSPORT,
            "subway_station": MarkerCategory.TRANSPORT,
            "light_rail_station": MarkerCategory.TRANSPORT,
            "bus_station": MarkerCategory.TRANSPORT,
            "taxi_stand": MarkerCategory.TRANSPORT,

            # SERVIZI E ALTRO
            "lodging": MarkerCategory.OTHER, # Alloggio
            "store": MarkerCategory.OTHER, # Negozio generico
            "point_of_interest": MarkerCategory.OTHER,
            "establishment": MarkerCategory.OTHER,
        }

        for g_type in gmaps_types:
            if g_type in mapping:
                return mapping[g_type]

        # Se nessun type specifico è stato trovato, restituiamo None
        # Sarà poi la pipeline a decidere se assegnare 'OTHER' o lasciare vuoto
        return None

    def _clean_query(self, query: str) -> str:
        """Estrae l'indirizzo utile se la query è un URL complesso."""
        if not query.startswith("http"):
            return query
        
        parsed_url = urlparse(query)
        params = parse_qs(parsed_url.query)
        
        # Prova a estrarre il parametro 'daddr' (destination address) per le directions
        if 'daddr' in params:
            return params['daddr'][0]
        
        # Prova a estrarre il parametro 'q'
        if 'q' in params:
            return params['q'][0]
        
        # Prova a estrarre il parametro 'query'
        if 'query' in params:
            return params['query'][0]
        
        # Se niente di cui sopra funziona, prova a estrarre dal path
        # Il path di Google Maps è: /maps/place/NOME+LUOGO,+INDIRIZZO/data=...
        path = parsed_url.path
        if '/maps/place/' in path:
            # Estrai la parte dopo '/maps/place/' e prima di '/data'
            match = re.search(r'/maps/place/([^/]+)(?:/data|$)', path)
            if match:
                place_name = match.group(1)
                # Decodifica gli spazi (+ diventa spazio, %20 diventa spazio)
                place_name = place_name.replace('+', ' ').replace('%20', ' ')
                # Rimuovi il checksum finale se presente (es: ,+%E3%80%92...)
                place_name = re.sub(r',\s*(?:%[0-9A-Fa-f]{2}|.)+$', '', place_name)
                if place_name:
                    return place_name
        
        return query

    def _extract_place_id(self, url: str) -> Optional[str]:
        """Tenta di estrarre il place_id o ftid da un URL Google Maps."""
        # Cerca ftid nei parametri
        match = re.search(r'ftid=([^&]+)', url)
        if match:
            return match.group(1)
        
        # Cerca place_id nei parametri
        match = re.search(r'place_id=([^&]+)', url)
        if match:
            return match.group(1)
        
        # Cerca il format 0x....:0x.... che appare nel path di Google Maps
        match = re.search(r'0x[a-f0-9]+:0x[a-f0-9]+', url)
        if match:
            return match.group(0)
        
        return None

    def _download_photos(self, photo_references: List[str], place_id: str, n: int) -> List[str]:
        """Scarica fisicamente le prime N immagini e restituisce i percorsi locali."""
        downloaded_paths = []
        # Prendiamo solo le prime N referenze
        for i, ref in enumerate(photo_references[:n]):
            params = {
                "maxwidth": 800, # Specifichiamo una larghezza max per non scaricare file giganti
                "photo_reference": ref,
                "key": self.api_key
            }
            try:
                # L'API farà un redirect all'immagine reale, requests lo segue in automatico
                response = requests.get(self.photo_url, params=params, stream=True, timeout=15)
                if response.status_code == 200:
                    file_name = f"{place_id}_photo_{i}.jpg"
                    file_path = os.path.join(self.media_folder, file_name)
                    
                    # Salviamo l'immagine a blocchi (stream) per non intasare la RAM
                    with open(file_path, 'wb') as f:
                        for chunk in response.iter_content(1024):
                            f.write(chunk)
                            
                    downloaded_paths.append(file_path)
            except Exception as e:
                print(f"Errore download foto {i} per {place_id}: {e}")
                
        return downloaded_paths

    def get_details_by_id(self, place_id: str, download_n_images: int = 0) -> Optional[Dict[str, Any]]:
        """Cerca i dettagli usando l'ID e aggiunge i nuovi campi."""
        params = {
            "place_id": place_id,
            # AGGIUNTI: formatted_address, types, website
            "fields": "name,geometry,place_id,url,photos,formatted_address,types,website",
            "key": self.api_key
        }
        try:
            response = requests.get(self.details_url, params=params, timeout=10).json()
            if response.get("status") == "OK":
                place = response["result"]
                return self._format_result(place, place.get("url"), download_n_images)
        except Exception as e:
            print(f"Errore Details API: {e}")
        return None

    def search_by_text(self, query: str, download_n_images: int = 0) -> Optional[Dict[str, Any]]:
        """Cerca tramite testo. Se trova il posto, usa i Details per avere tutti i dati completi."""
        clean_q = self._clean_query(query)
        params = {"query": clean_q, "key": self.api_key}
        
        try:
            response = requests.get(self.text_search_url, params=params, timeout=10).json()
            if response.get("status") == "OK" and response.get("results"):
                place = response["results"][0]
                place_id = place.get('place_id')
                
                # TRUCCO IMPORTANTE: TextSearch NON restituisce il 'website' o l'URL ufficiale.
                # Quindi, appena troviamo il place_id, chiamiamo i Details per avere dati uniformi!
                if place_id:
                    details = self.get_details_by_id(place_id, download_n_images)
                    if details: return details
                
                # Fallback di emergenza se per qualche motivo il Details fallisce
                maps_url = f"https://www.google.com/maps/search/?api=1&query={place['geometry']['location']['lat']},{place['geometry']['location']['lng']}&query_place_id={place_id}"
                return self._format_result(place, maps_url, download_n_images)
        except Exception as e:
            print(f"Errore TextSearch API: {e}")
        return None

    def _format_result(self, place: Dict, maps_url: str, download_n_images: int) -> Dict[str, Any]:
        """Normalizza i dati ed esegue il download delle immagini se richiesto."""
        # Estraiamo tutte le referenze fotografiche disponibili
        photo_refs = [p.get("photo_reference") for p in place.get("photos", [])]
        local_photos = []
        
        # Se è richiesto il download e ci sono foto, scarichiamole
        if download_n_images > 0 and photo_refs:
            local_photos = self._download_photos(photo_refs, place.get("place_id"), download_n_images) # type: ignore

        # Mappiamo la categoria
        gmaps_types = place.get("types", [])
        category = self._map_google_types_to_category(gmaps_types)

        return {
            "name": place.get("name"),
            "lat": float(place["geometry"]["location"]["lat"]),
            "lng": float(place["geometry"]["location"]["lng"]),
            "google_place_id": place.get("place_id"),
            "address": place.get("formatted_address"),
            "category": category, # CAMPO AGGIUNTO!
            "google_maps_tags": gmaps_types, # Rinomino per chiarezza
            "website": place.get("website"),
            "google_maps_url": maps_url,
            "local_photos": local_photos
        }

    def resolve(self, query: str, download_n_images: int = 5) -> Optional[Dict[str, Any]]:
        """Entry point principale della classe."""
        if query.startswith("http"):
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.head(query, allow_redirects=True, headers=headers, timeout=10)
                resolved_url = response.url
                
                place_id = self._extract_place_id(resolved_url)
                if place_id:
                    details = self.get_details_by_id(place_id, download_n_images)
                    if details: return details
                
                return self.search_by_text(resolved_url, download_n_images)
                
            except Exception as e:
                print(f"Errore risoluzione URL: {e}")

        # Ricerca standard per testo
        return self.search_by_text(query, download_n_images)
    

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()  # Carica le variabili d'ambiente dal file .env
    geocoder = GoogleMapsGeocoder()
    
    # Esempio di test
    test_queries = [
        "Colosseo, Roma",
        "https://maps.app.goo.gl/KizNVuFSe5pfTBrf7?g_st=ic"
    ]
    
    for query in test_queries:
        result = geocoder.resolve(query, download_n_images=5)
        print(f"Query: {query}\nResult: {result}\n{'-'*40}")