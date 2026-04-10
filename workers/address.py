import hashlib
import os
from uuid import uuid4

import requests
from dotenv import load_dotenv

from data.database import Database
from models.location import Location, MarkerCategory

load_dotenv()
db = Database("sqlite:///data/database.db")


def _make_checksum(name: str, lat: float, lng: float) -> str:
    payload = f"{name.strip().lower()}|{lat:.6f}|{lng:.6f}"
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def _infer_location_category(text: str) -> MarkerCategory:
    t = (text or "").lower()

    if any(k in t for k in ["food", "cibo", "ramen", "sushi", "izakaya", "restaurant", "brewery", "market"]):
        return MarkerCategory.FOOD
    if any(k in t for k in ["station", "airport", "metro", "train"]):
        return MarkerCategory.TRANSPORT
    if any(k in t for k in ["temple", "shrine", "museum", "castle"]):
        return MarkerCategory.CULTURE
    if any(k in t for k in ["city", "tokyo", "kyoto", "osaka", "kamakura"]):
        return MarkerCategory.CITY

    return MarkerCategory.OTHER


def search_place(query: str) -> dict | None:
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("[Address Worker] GOOGLE_MAPS_API_KEY not found.")
        return None

    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"query": query, "key": api_key}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

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
            google_maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_name}&query_place_id={place_id}"
        else:
            google_maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_query}"

        return {
            "name": place.get("name") or query,
            "lat": float(lat),
            "lng": float(lng),
            "google_maps_url": google_maps_url,
        }
    except Exception as e:
        print(f"[Address Worker] Error searching place: {e}")
        return None


if __name__ == "__main__":
    messages = db.get_messages_by_category("address")
    added_locations = 0

    for message in messages:
        if message.status == "done":
            continue

        query = (message.raw_text or "").strip()
        if not query:
            db.update_message_status(message.telegram_id, "discarded", category="address")
            continue

        print(f"[Address Worker] Processing message {message.telegram_id}")
        db.update_message_status(message.telegram_id, "processed", category="address")

        result = search_place(query)
        if not result:
            print("[Address Worker] No Google Maps result.")
            continue

        name = (result["name"] or query).strip()[:255]
        lat = float(result["lat"])
        lng = float(result["lng"])
        checksum = _make_checksum(name, lat, lng)

        if not db.get_location_by_checksum(checksum):
            location = Location(
                id=uuid4().hex,
                name=name,
                lat=lat,
                lng=lng,
                description=query,
                google_maps_url=result["google_maps_url"],
                source_url=f"telegram:{message.telegram_id}",
                category=_infer_location_category(query),
                checksum=checksum,
                is_draft=False,
                platform="address",
            )
            db.insert_location(location)
            added_locations += 1

        db.update_message_status(message.telegram_id, "done", category="address")

    print(f"[Address Worker] Done. Added {added_locations} new location(s).")
