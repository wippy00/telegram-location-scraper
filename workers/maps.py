import os
from uuid import uuid4
from pathlib import Path
import requests
from dotenv import load_dotenv
load_dotenv()
from data.database import Database
from models.location import Location, MarkerCategory
from workers.google_maps_common import make_location_checksum, search_place

db = Database("sqlite:///data/database.db")
ROOT_DIR = Path(__file__).resolve().parents[1]
PHOTO_DIR = ROOT_DIR / "frontend" / "static" / "location_photos"


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


def _slugify(value: str) -> str:
    safe_value = "".join(character.lower() if character.isalnum() else "-" for character in value)
    safe_value = "-".join(part for part in safe_value.split("-") if part)
    return safe_value[:60] or "location"


def _download_place_photo(photo_reference: str, *, name: str) -> str | None:
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("[Google Maps] WARNING: GOOGLE_MAPS_API_KEY not found in environment.")
        return None

    PHOTO_DIR.mkdir(parents=True, exist_ok=True)

    filename = f"{_slugify(name)}_{uuid4().hex}.jpg"
    target_path = PHOTO_DIR / filename

    try:
        response = requests.get(
            "https://maps.googleapis.com/maps/api/place/photo",
            params={
                "maxwidth": 800,
                "photo_reference": photo_reference,
                "key": api_key,
            },
            timeout=20,
        )
        response.raise_for_status()

        content_type = (response.headers.get("content-type") or "").lower()
        if "png" in content_type:
            target_path = target_path.with_suffix(".png")
        elif "webp" in content_type:
            target_path = target_path.with_suffix(".webp")

        target_path.write_bytes(response.content)
        print(f"[Google Maps] Photo saved to {target_path}")
        return f"/location_photos/{target_path.name}"
    except Exception as error:
        print(f"[Google Maps] Error downloading photo for '{name}': {error}")
        return None

def _fetch_place_photo_references(place_id: str) -> list[str]:
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("[Google Maps] WARNING: GOOGLE_MAPS_API_KEY not found in environment.")
        return []

    try:
        response = requests.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={
                "place_id": place_id,
                "fields": "photos",
                "key": api_key,
            },
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get("status") != "OK":
            print(f"[Google Maps] Place details returned status '{payload.get('status')}' for photo lookup")
            return []

        photos = payload.get("result", {}).get("photos") or []
        return [photo.get("photo_reference") for photo in photos if photo.get("photo_reference")]
    except Exception as error:
        print(f"[Google Maps] Error fetching photo references for '{place_id}': {error}")
        return []


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

    checksum = make_location_checksum(name, lat_f, lng_f)
    existing = db.get_location_by_checksum(checksum)
    if existing:
        return False

    location = Location(
        id=uuid4().hex,
        name=name,
        lat=lat_f,
        lng=lng_f,
        telegram_message_id=reel.telegram_id,
        description=(
            place_data.get("description")
            or place_data.get("evidence_text")
            or ""
        ).strip() or None,
        google_maps_url=(place_data.get("google_maps_url") or "").strip() or None,
        source_url=reel.source_url,
        photo_paths=place_data.get("photo_paths"),
        category=_to_marker_category(place_data.get("category")),
        checksum=checksum,
        platform="instagram",
    )
    db.insert_location(location)
    return True

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

                        photo_references = gmaps_result.get("photo_references") or []
                        if not photo_references and gmaps_result.get("place_id"):
                            photo_references = _fetch_place_photo_references(gmaps_result["place_id"])

                        photo_paths = []
                        for photo_reference in photo_references[:3]:
                            photo_path = _download_place_photo(photo_reference, name=gmaps_result["name"])
                            if photo_path:
                                photo_paths.append(photo_path)

                        if photo_paths:
                            place_data["photo_paths"] = photo_paths

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
