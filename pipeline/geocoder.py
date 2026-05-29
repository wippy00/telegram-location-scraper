import os
import re
import requests
import urllib.parse
from typing import Optional, Dict, Any, List

# from models.location import MarkerCategory

from enum import Enum
class MarkerCategory(str, Enum):
    FOOD = "food"
    LANDMARK = "landmark"
    FUN = "fun"
    CULTURE = "culture"
    TRANSPORT = "transport"
    CITY = "city"
    OTHER = "other"


class GoogleMapsGeocoder:
    def __init__(self, media_folder: str = "media/places"):
        self.api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        self.text_search_url = "https://places.googleapis.com/v1/places:searchText"
        # self.details_url = "https://maps.googleapis.com/maps/api/place/details/json"
        # self.photo_url = "https://maps.googleapis.com/maps/api/place/photo"
        
        # Cartella dove salveremo le immagini
        self.media_folder = media_folder
        os.makedirs(self.media_folder, exist_ok=True)


    ## HELPER FUNCTIONS ##
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

    def _download_photos(self, photo_references: List[str], place_id: str, n: int) -> List[str]:
        """Scarica fisicamente le prime N immagini (New API) e restituisce i percorsi locali."""
        downloaded_paths = []
        
        # Le 'photo_references' passate da _format_result ora sono in formato:
        # "places/ChIJ.../photos/AeUB..."
        for i, photo_name in enumerate(photo_references[:n]):
            file_name = f"{place_id}_photo_{i}.jpg"
            file_path = os.path.join(self.media_folder, file_name)
            
            # Se la foto esiste già su disco, saltiamo il download
            if os.path.exists(file_path):
                print(f"[GoogleMapsGeocoder] Foto {i} per {place_id} già presente. Skip download.")
                downloaded_paths.append(file_path)
                continue

            # 1. Il nuovo URL incorpora dinamicamente il nome della foto
            url = f"https://places.googleapis.com/v1/{photo_name}/media"
            
            # 2. Il parametro ora si chiama maxWidthPx in camelCase
            params = {
                "maxWidthPx": 800, 
                "key": self.api_key
            }
            
            try:
                # 3. Facciamo la chiamata GET. Google restituirà un redirect (302) 
                # all'immagine sulla CDN, e requests lo seguirà in automatico grazie a stream=True.
                response = requests.get(url, params=params, stream=True, timeout=15)
                
                if response.status_code == 200:
                    # Salviamo l'immagine a blocchi (stream) per non intasare la RAM (Logica perfetta!)
                    with open(file_path, 'wb') as f:
                        for chunk in response.iter_content(1024):
                            f.write(chunk)
                            
                    downloaded_paths.append(file_path)
                else:
                    print(f"Errore download foto {i} per {place_id}. Codice HTTP: {response.status_code}")
                    
            except Exception as e:
                print(f"Errore download foto {i} per {place_id}: {e}")
                
        return downloaded_paths

    def _format_result(self, place: Dict, maps_url: str, download_n_images: int) -> Dict[str, Any]:
        """Normalizza i dati ed esegue il download delle immagini se richiesto."""
        
        # 1. Le foto: Nelle nuove API, l'ID della foto si trova dentro la chiave "name"
        # Il formato che restituisce è ad esempio: "places/ChIJ.../photos/AeUB..."
        photo_refs = [p.get("name") for p in place.get("photos", [])]
        local_photos = []
        
        # 2. Il Place ID: Nelle nuove API si chiama semplicemente "id"
        google_place_id = place.get("id")
        
        # Se è richiesto il download e ci sono foto, scarichiamole
        if download_n_images > 0 and photo_refs and google_place_id:
            local_photos = self._download_photos(photo_refs, google_place_id, download_n_images)

        # I tipi rimangono invariati come lista di stringhe
        gmaps_types = place.get("types", [])
        category = self._map_google_types_to_category(gmaps_types)

        return {
            # Il nome ora è annidato in displayName -> text
            "name": place.get("displayName", {}).get("text"),
            
            # Le coordinate ora sono dentro location -> latitude/longitude (non più geometry)
            "lat": float(place.get("location", {}).get("latitude", 0.0)),
            "lng": float(place.get("location", {}).get("longitude", 0.0)),
            
            "google_place_id": google_place_id,
            
            # Ora è in camelCase
            "address": place.get("formattedAddress"),
            
            "category": category, 
            "google_maps_tags": gmaps_types, 
            
            # Il sito web ora si chiama websiteUri
            "website": place.get("websiteUri"),
            
            "google_maps_url": maps_url,
            "local_photos": local_photos
        }


    ## PARSER FOR DIFFERENT GOOGLE MAPS URL FORMATS ##
    def parse_google_maps_url_place(self, url: str) -> Dict[str, Optional[str]]:
        """
        Estrae i dati da un URL di Google Maps in formato /place/.
        
        Restituisce un dizionario con:
            - place_name:   nome del luogo (decodificato)
            - address:      indirizzo (decodificato, se presente nel path)
            - place_id:     ID del luogo (dal parametro 'data')
            - map_type:     tipo di mappa (es. 'satellite', 'street_view')
            - raw_data:     contenuto grezzo del parametro 'data'
        """
        
        # 1. Analisi generale dell'URL
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
        
        # 2. Estrazione della parte del luogo e del parametro 'data' dal path
        #    Esempio: /place/Shinjuku+Sports+Center,.../data=!4m2!...
        place_str = ""
        data_str = ""
        
        # Separiamo sul primo "/data="
        if "/data=" in path:
            place_str, data_str = path.split("/data=", 1)
        else:
            # Fallback: se non c'è /data= (es. URL abbreviato), usiamo tutto il path
            place_str = path
        
        # 3. Decodifica del nome e dell'indirizzo
        # Rimuoviamo il prefisso "/place/"
        if place_str.startswith("/maps/place/"):
            place_str = place_str[12:]  # lunghezza di "/maps/place/"
        
        # Decodifica dei caratteri URL-encoded (es. %E6%96%B0 -> 新)
        place_decoded = urllib.parse.unquote(place_str)
        place_decoded = place_decoded.replace("+", " ")  # Sostituiamo i + con spazi (Google Maps usa + per gli spazi)
        
        if "/" in place_decoded:
            # Se c'è una barra, prendiamo solo la parte prima della barra (a volte c'è un ID o altre info dopo)
            parts = place_decoded.split("/")
        else:
            # Il nome è la prima parte prima della virgola, il resto è l'indirizzo
            parts = place_decoded.split(",")

        name = parts[0].strip() if parts else None


        address = ",".join(parts[1:]).strip() if len(parts) > 1 else None
        if address and "@" in address:
            address = ",".join(address[1:].split(",")[:2])
        
        # 4. Analisi del parametro 'data'
        place_id = None
        map_type = None
        
        if data_str:
            # Rimuoviamo eventuali parametri query (es. ?utm_source=...)
            if "?" in data_str:
                data_str = data_str.split("?")[0]
            
            # Cerchiamo il place ID: token !1s seguito dal valore
            place_match = re.search(r"!1s([^!]+)", data_str)
            if place_match:
                place_id = place_match.group(1)
            
            # Cerchiamo il tipo di mappa: ultimo token !1e (secondo la documentazione)
            map_match = re.findall(r"!1e(\d+)", data_str)
            if map_match:
                # Mappa l'ultimo valore numerico a una stringa descrittiva
                map_codes = {"0": "street_map", "1": "street_view", "2": "user_photos", "3": "satellite"}
                last_code = map_match[-1]
                map_type = map_codes.get(last_code, f"unknown_{last_code}")
        
        return {
            "place_name": name,
            "address": address,
            "place_id": place_id,
            "map_type": map_type,
            "raw_data": data_str if data_str else None
        }

    def parse_google_maps_url_query(self, url: str) -> Dict[str, Optional[str]]:
        """
        Estrae i dati da un URL di Google Maps nel formato /maps?q=...&ftid=...
        
        Restituisce un dizionario con:
            - place_name:   nome del luogo (decodificato)
            - address:      indirizzo (decodificato)
            - place_id:     ID del luogo (dal parametro 'ftid')
            - query_raw:    contenuto grezzo del parametro 'q'
            - ftid_raw:     contenuto grezzo del parametro 'ftid'
            - entry:        tipo di voce (es. 'gps')
            - g_st:         lingua (es. 'it')
        """
        
        # Analizza l'URL e i parametri di query
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        
        # Estrai i parametri principali
        q = params.get('q', [None])[0]
        ftid = params.get('ftid', [None])[0]
        entry = params.get('entry', [None])[0]
        g_st = params.get('g_st', [None])[0]
        
        # Decodifica la query e separa nome e indirizzo
        place_name = None
        address = None
        if q:
            query_decoded = urllib.parse.unquote(q)
            # Il nome è la prima parte prima della virgola, il resto è l'indirizzo
            parts = query_decoded.split(",", 1)
            place_name = parts[0].strip() if parts else None
            address = parts[1].strip() if len(parts) > 1 else None
        
        # Place ID (ftid)
        place_id = ftid if ftid else None
        
        return {
            "place_name": place_name,
            "address": address,
            "place_id": place_id,
            "entry": entry,
            "g_st": g_st,
            "query_raw": q,
            "ftid_raw": ftid
        }
    
    def parse_google_maps_url_directions(self, url: str) -> Dict[str, Optional[object]]:
        """
        Estrae i dati da un URL di Google Maps Directions.
        
        Restituisce:
            - origin_address:       indirizzo di partenza (decodificato)
            - destination_address:  indirizzo di destinazione (decodificato)
            - origin_feature_id:    Feature ID dell'origine (es. 0x...:0x...)
            - destination_feature_id: Feature ID della destinazione
            - origin_cid:           CID dell'origine (decimale)
            - destination_cid:      CID della destinazione (decimale)
            - directions_flag:      flag della modalità di trasporto
            - geocode_list:         lista delle stringhe geocode grezze
            - entry:                tipo di voce (es. 'gps')
            - g_st:                 lingua (es. 'ic')
        """
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        
        saddr = params.get('saddr', [None])[0]
        daddr = params.get('daddr', [None])[0]
        geocode = params.get('geocode', [None])[0]
        dirflg = params.get('dirflg', [None])[0]
        ftid = params.get('ftid', [None])[0]
        entry = params.get('entry', [None])[0]
        g_st = params.get('g_st', [None])[0]
        
        origin_address = urllib.parse.unquote(saddr) if saddr else None
        destination_address = urllib.parse.unquote(daddr) if daddr else None
        
        origin_feature_id = None
        destination_feature_id = None
        origin_cid = None
        destination_cid = None
        
        if ftid:
            ids = ftid.split(';')
            if len(ids) >= 2:
                destination_feature_id = ids[0]
                origin_feature_id = ids[1]
            elif len(ids) == 1:
                destination_feature_id = ids[0]
            # Converti in CID
            if destination_feature_id:
                right_hex = destination_feature_id.split(':')[1]
                destination_cid = str(int(right_hex, 16))
            if origin_feature_id:
                right_hex = origin_feature_id.split(':')[1]
                origin_cid = str(int(right_hex, 16))
        
        geocode_list = geocode.split(';') if geocode else []
        
        return {
            "origin_address": origin_address,
            "destination_address": destination_address,
            "origin_feature_id": origin_feature_id,
            "destination_feature_id": destination_feature_id,
            "origin_cid": origin_cid,
            "destination_cid": destination_cid,
            "directions_flag": dirflg,
            "geocode_list": geocode_list,
            "entry": entry,
            "g_st": g_st
        }


    ## MAIN FUNCTION TO FETCH PLACE DETAILS USING TEXT SEARCH API ##
    def fetch_place_details_by_query(self, query: str, download_n_images: int = 5, lat: str = "", lng: str = "") -> Optional[Dict[str, Any]]:
        """Cerca i dettagli usando la query e aggiunge i nuovi campi."""

        url = self.text_search_url
        api_key = self.api_key

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.location,places.id,places.googleMapsUri,places.photos,places.formattedAddress,places.types,places.websiteUri"
        }

        payload: dict[str, Any] = {
            "textQuery": query,
            # "languageCode": "it"
        }

        if lat and lng:
            payload["locationBias"] = {
                "circle": {
                    "center": {
                        "latitude": float(lat),
                        "longitude": float(lng)
                    },
                    "radius": 500  # Raggio di 500 metri
                }
            }

        print(f"Payload: {payload}")
            
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            data = response.json()

            if "places" in data and len(data["places"]) > 0:
                place = data["places"][0]
                
    
                maps_url = place.get("googleMapsUri")
                
                # Esempio di stampa dei dati per verifica:
                print(f"Trovato: {place.get('displayName', {}).get('text')}")
                print(f"Place ID: {place.get('id')}")
                
                return self._format_result(place, maps_url, download_n_images)
            else:
                print(f"Nessun risultato trovato per la query: {query}")
                print(f"Risposta API: {data}")
                
        except Exception as e:
            print(f"Errore Details API: {e}")
            
        return None


    ## MAIN ENTRY POINT ##
    def resolve(self, query: str, download_n_images: int = 5) -> Optional[Dict[str, Any]]:
        """Entry point principale della classe."""

        if query.startswith("http"):
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                    'Accept-Language': 'en-US,en;q=0.9'
                }

                response = requests.head(query, allow_redirects=True, headers=headers, timeout=10)
                final_url = response.url
                
                if re.search(r'https://www\.google\.[a-z]+/maps/place/', final_url):
                    print("place")
                    
                    result = self.parse_google_maps_url_place(final_url)
                    # place_id = result.get("place_id")
                    place_name = result.get("place_name")
                    place_address = result.get("address", "")

                    print(ascii(place_address))
                    
                    if place_name:
                        
                        address_parts = [part.strip() for part in place_address.split(",")] if place_address else []

                        if len(address_parts) >= 2:
                            try:
                                lat = float(address_parts[0])
                                lng = float(address_parts[1])
                                return self.fetch_place_details_by_query(place_name, download_n_images, lat=str(lat), lng=str(lng))
                            except (TypeError, ValueError):
                                pass

                        combined_query = f"{place_name} {place_address}".strip()
                        return self.fetch_place_details_by_query(combined_query, download_n_images)

                elif re.search(r'https://maps\.google\.[a-z]+/maps\?q=', final_url):
                    print("query")
                    result = self.parse_google_maps_url_query(final_url)
                    # place_id = result.get("place_id")
                    place_name = result.get("place_name")
                    place_address = result.get("address")
                    # place_coordinates = result.get("query_raw")

                    if place_name:
                        # print(f"{place_name} \n {place_address}")
                        # print(fetch_place_details_by_query(f"{place_name}  {place_address}"))
                        return self.fetch_place_details_by_query(f"{place_name}  {place_address}", download_n_images)
                    
                elif re.search(r'https://maps\.google\.[a-z]+/maps\?geocode=', final_url):
                    print("directions")
                    result = self.parse_google_maps_url_directions(final_url)
                    # place_id = result.get("destination_place_id")
                    place_address = result.get("destination_address")
                    
                    if place_address:
                        # print(place_address)
                        # print(fetch_place_details_by_query(f"{place_name}"))
                        return self.fetch_place_details_by_query(f"{place_address}", download_n_images)

                else:
                    print(final_url)
                
            except Exception as e:
                print(f"Errore risoluzione URL: {e}")

        return self.fetch_place_details_by_query(query, download_n_images)

        

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()  # Carica le variabili d'ambiente dal file .env
    geocoder = GoogleMapsGeocoder()
    
    # Esempio di test
    test_queries = [
        # "Colosseo, Roma",
        # "https://maps.app.goo.gl/KizNVuFSe5pfTBrf7?g_st=ic"
        # "https://maps.app.goo.gl/nMyqgUZdmm1ivpYp8"
        "https://maps.app.goo.gl/fNmnYP1Jz9wW6Jg8A"
    ]
    
    for query in test_queries:
        result = geocoder.resolve(query, download_n_images=0)
        print(f"Query/Link: {query}\nResult: {result}\n{'-'*40}")