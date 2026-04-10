import os
import hashlib
from uuid import uuid4
import requests
from dotenv import load_dotenv
load_dotenv()
from data.database import Database
from models.location import Location, MarkerCategory

db = Database("sqlite:///data/database.db")


def _to_marker_category(value: str | None) -> MarkerCategory:
    raw = (value or "").strip().lower()
    mapping = {
        "food": MarkerCategory.FOOD,
        "landmark": MarkerCategory.LANDMARK,
        "fun": MarkerCategory.FUN,
        "culture": MarkerCategory.CULTURE,
        "transport": MarkerCategory.TRANSPORT,
        "city": MarkerCategory.CITY,
    }
    return mapping.get(raw, MarkerCategory.OTHER)


def _make_checksum(name: str, lat: float, lng: float) -> str:
    payload = f"{name.strip().lower()}|{lat:.6f}|{lng:.6f}"
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def _save_location_from_place(reel, place_data: dict) -> bool:
    lat = place_data.get("lat")
    lng = place_data.get("lng")

    if lat is None or lng is None:
        return False

    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return False

    name = (place_data.get("name") or place_data.get("normalized_name") or "").strip()
    if not name:
        return False

    checksum = _make_checksum(name, lat_f, lng_f)
    existing = db.get_location_by_checksum(checksum)
    if existing:
        return False

    location = Location(
        id=uuid4().hex,
        name=name,
        lat=lat_f,
        lng=lng_f,
        description=(
            place_data.get("description")
            or place_data.get("evidence_text")
            or ""
        ).strip() or None,
        google_maps_url=(place_data.get("google_maps_url") or "").strip() or None,
        source_url=reel.source_url,
        category=_to_marker_category(place_data.get("category")),
        checksum=checksum,
        is_draft=False,
        platform="instagram",
    )
    db.insert_location(location)
    return True

def search_place(query: str) -> dict | None:
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("[Google Maps] WARNING: GOOGLE_MAPS_API_KEY not found in environment.")
        return None

    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"query": query, "key": api_key}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        if not data.get("results"):
            return None

        place = data["results"][0]
        lat = place["geometry"]["location"]["lat"]
        lng = place["geometry"]["location"]["lng"]
        place_id = place.get("place_id")
        
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        encoded_name = urllib.parse.quote(place.get("name", query))
        
        if place_id:
            gmaps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_name}&query_place_id={place_id}"
        else:
            gmaps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_query}"
        
        return {
            "name": place.get("name"),
            "lat": lat,
            "lng": lng,
            "google_maps_url": gmaps_url
        }
    except Exception as e:
        print(f"[Google Maps] Error searching for '{query}': {e}")
        return None


if __name__ == "__main__":
    reels = db.get_reels_by_pipeline_status("pending_maps")
    
    for reel in reels:
        print(f"[Maps Worker] Processing reel: {reel.shortcode}")
        added_locations = 0
        
        if reel.ai_places_json:
            enriched_places = []
            for place_data in reel.ai_places_json:
                google_maps_query = place_data.get("google_maps_query")
                if google_maps_query:
                    print(f"[Google Maps] Searching: {google_maps_query}")
                    gmaps_result = search_place(google_maps_query)
                    if gmaps_result:
                        place_data["lat"] = gmaps_result["lat"]
                        place_data["lng"] = gmaps_result["lng"]
                        place_data["google_maps_url"] = gmaps_result["google_maps_url"]
                        print(f"[Google Maps] Found: {gmaps_result['name']} at {gmaps_result['lat']}, {gmaps_result['lng']}")
                    else:
                        print(f"[Google Maps] No results found for: {google_maps_query}")

                if _save_location_from_place(reel, place_data):
                    added_locations += 1
                enriched_places.append(place_data)
                
            reel.ai_places_json = enriched_places
            
        reel.pipeline_status = "pending_response"
        
        db.upsert_instagram_reel(reel)
        db.update_message_status(reel.telegram_id, "processed", category="instagram")
        print(f"[Maps Worker] Maps processing finished. Added {added_locations} new location(s). Moving to pending_response.")
