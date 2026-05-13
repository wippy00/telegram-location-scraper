import os
from dotenv import load_dotenv
import asyncio
import requests
import urllib.parse
from typing import Dict, Optional, Any

from database.engine import get_engine, init_db
from database.crud import DatabaseCRUD
from models import PipelineStatus, PlatformType
from pipeline.categorizer import categorize_message

from pipeline.router import extract_locations_from_message

db_path = os.getenv("DATABASE_PATH", "sqlite:///database/data.db")
engine = get_engine(db_path)
init_db(engine)
db = DatabaseCRUD(engine)

telegram_messages = db.get_messages()

import re
import time


def _format_result(place: Dict, maps_url: str, download_n_images: int) -> Dict[str, Any]:
    """Normalizza i dati ed esegue il download delle immagini se richiesto."""

    # Estraiamo le coordinate in modo sicuro
    location = place.get("location", {})
    lat = location.get("latitude")
    lng = location.get("longitude")

    return {
        # 'displayName' è un dizionario che contiene 'text' e 'languageCode'
        "name": place.get("displayName", {}).get("text"),
        
        # Gestione sicura nel caso lat/lng non siano presenti
        "lat": float(lat) if lat is not None else None,
        "lng": float(lng) if lng is not None else None,
        
        # 'id' sostituisce 'place_id'
        "google_place_id": place.get("id"),
        
        # Le nuove API usano il camelCase
        "address": place.get("formattedAddress"),
        "website": place.get("websiteUri"),
        
        "google_maps_url": maps_url,
    }

def extract_url_from_text(text: str) -> str | None:
    """Trova il link di Google Maps nascosto in mezzo alle parole del messaggio."""
    match = re.search(r'(https?://(?:www\.)?(?:maps\.app\.goo\.gl|goo\.gl/maps|maps\.google\.com|google\.com/maps)[^\s]+)', text)
    return match.group(1) if match else None


def parse_google_maps_url_place(url: str) -> Dict[str, Optional[str]]:
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

def parse_google_maps_url_query(url: str) -> Dict[str, Optional[str]]:
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

def parse_google_maps_url_directions(url: str) -> Dict[str, Optional[object]]:
    """
    Estrae i dati da un URL di Google Maps che rappresenta un percorso (directions).
    
    Restituisce un dizionario con:
        - origin_address:       indirizzo di partenza (decodificato)
        - destination_address:  indirizzo di destinazione (decodificato)
        - origin_place_id:      place ID dell'origine (se presente)
        - destination_place_id: place ID della destinazione (se presente)
        - directions_flag:      flag della modalità di trasporto (es. 'rBSTR')
        - geocode_list:         lista delle stringhe geocode grezze (una per punto)
        - entry:                tipo di voce (es. 'gps')
        - g_st:                 lingua (es. 'ic')
    """
    
    # Analizza l'URL e i parametri di query
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    
    # Estrai i parametri principali
    saddr = params.get('saddr', [None])[0]
    daddr = params.get('daddr', [None])[0]
    geocode = params.get('geocode', [None])[0]
    dirflg = params.get('dirflg', [None])[0]
    ftid = params.get('ftid', [None])[0]
    entry = params.get('entry', [None])[0]
    g_st = params.get('g_st', [None])[0]
    
    # Decodifica degli indirizzi
    origin_address = urllib.parse.unquote(saddr) if saddr else None
    destination_address = urllib.parse.unquote(daddr) if daddr else None
    
    # Suddivisione dei place ID (ordine tipico: destinazione, origine)
    origin_place_id = None
    destination_place_id = None
    if ftid:
        ids = ftid.split(';')
        if len(ids) >= 2:
            destination_place_id = ids[0]
            origin_place_id = ids[1]
        elif len(ids) == 1:
            destination_place_id = ids[0]
    
    # Suddivisione del geocode in una lista
    geocode_list = geocode.split(';') if geocode else []
    
    return {
        "origin_address": origin_address,
        "destination_address": destination_address,
        "origin_place_id": origin_place_id,
        "destination_place_id": destination_place_id,
        "directions_flag": dirflg,
        "geocode_list": geocode_list,
        "entry": entry,
        "g_st": g_st
    }

def parse_google_maps_url_directions_v2(url: str) -> Dict[str, Optional[object]]:
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


def fetch_place_details_by_id(place_id: str, download_n_images: int = 5) -> Optional[Dict[str, Any]]:
    """Cerca i dettagli usando l'ID e aggiunge i nuovi campi."""
    params = {
        "place_id": place_id,
        "fields": "name,geometry,place_id,url,photos,formatted_address,types,website",
        "key": "AIzaSyA09vdn0ONnk7gxHiDqc9YVq3eGmhhRWgE"
    }
    try:
        response = requests.get("https://maps.googleapis.com/maps/api/place/details/json", params=params, timeout=10).json()
        if response.get("status") == "OK":
            place = response["result"]
            return _format_result(place, place.get("url"), 5)
    except Exception as e:
        print(f"Errore Details API: {e}")
    return None

def fetch_place_details_by_query(query: str, download_n_images: int = 5) -> Optional[Dict[str, Any]]:
    """Cerca i dettagli usando la query e aggiunge i nuovi campi."""

    url = "https://places.googleapis.com/v1/places:searchText"
    api_key = "AIzaSyA09vdn0ONnk7gxHiDqc9YVq3eGmhhRWgE"

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.location,places.id,places.googleMapsUri,places.photos,places.formattedAddress,places.types,places.websiteUri"
    }

    payload = {
        "textQuery": query,
        "languageCode": "it"
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        data = response.json()

        if "places" in data and len(data["places"]) > 0:
            place = data["places"][0]
            
  
            maps_url = place.get("googleMapsUri")
            
            # Esempio di stampa dei dati per verifica:
            print(f"Trovato: {place.get('displayName', {}).get('text')}")
            print(f"Place ID: {place.get('id')}")
            
            return _format_result(place, maps_url, download_n_images)
        else:
            print(f"Nessun risultato trovato per la query: {query}")
            
    except Exception as e:
        print(f"Errore Details API: {e}")
        
    return None



headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9'
}

for msg in telegram_messages:

    msg.platform_detected = categorize_message(msg.raw_text)

    if msg.platform_detected == PlatformType.GOOGLE_MAPS:
        
        short_url = extract_url_from_text(msg.raw_text)
        if not short_url:
            continue

        response = requests.head(short_url, allow_redirects=True, headers=headers, timeout=10)
        final_url = response.url
        
        if re.search(r'https://www\.google\.[a-z]+/maps/place/', final_url):
            print("place")
            
            result = parse_google_maps_url_place(final_url)
            # place_id = result.get("place_id")
            place_name = result.get("place_name")
            place_address = result.get("address")
            
            if place_name:
                # print(f"{place_name} \n {place_address}")
                print(fetch_place_details_by_query(f"{place_name}  {place_address}"))

    
        elif re.search(r'https://maps\.google\.[a-z]+/maps\?q=', final_url):
            print("query")
            result = parse_google_maps_url_query(final_url)
            # place_id = result.get("place_id")
            place_name = result.get("place_name")
            place_address = result.get("address")

            # place_coordinates = result.get("query_raw")
            
            if place_name:
                # print(f"{place_name} \n {place_address}")
                print(fetch_place_details_by_query(f"{place_name}  {place_address}"))
          
            
        elif re.search(r'https://maps\.google\.[a-z]+/maps\?geocode=', final_url):
            print("directions")
            result = parse_google_maps_url_directions_v2(final_url)
            # place_id = result.get("destination_place_id")
            place_address = result.get("destination_address")
            
            if place_address:
                # print(place_address)
                print(fetch_place_details_by_query(f"{place_name}"))

        else:
            print(final_url)

        print("\n\n")
