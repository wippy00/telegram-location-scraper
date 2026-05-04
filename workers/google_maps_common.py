import hashlib
import os
from pathlib import Path
from typing import Any
from uuid import uuid4
from urllib.parse import quote

import requests
from dotenv import load_dotenv


load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[1]
PHOTO_DIR = ROOT_DIR / "frontend" / "static" / "location_photos"


def make_location_checksum(name: str, lat: float, lng: float) -> str:
    payload = f"{name.strip().lower()}|{lat:.6f}|{lng:.6f}"
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def build_google_maps_url(query: str, *, place_name: str | None = None, place_id: str | None = None) -> str:
    encoded_query = quote(query)
    encoded_name = quote(place_name or query)

    if place_id:
        return f"https://www.google.com/maps/search/?api=1&query={encoded_name}&query_place_id={place_id}"

    return f"https://www.google.com/maps/search/?api=1&query={encoded_query}"


def search_place(query: str, *, log_prefix: str = "[Google Maps]") -> dict[str, Any] | None:
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print(f"{log_prefix} WARNING: GOOGLE_MAPS_API_KEY not found in environment.")
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
        photos = place.get("photos") or []
        photo_references = [photo.get("photo_reference") for photo in photos if photo.get("photo_reference")]

        return {
            "name": place.get("name") or query,
            "lat": float(lat),
            "lng": float(lng),
            "google_maps_url": build_google_maps_url(query, place_name=place.get("name", query), place_id=place_id),
            "place_id": place_id,
            "photo_references": photo_references,
        }
    except Exception as error:
        print(f"{log_prefix} Error searching for '{query}': {error}")
        return None


def fetch_place_photo_references(place_id: str, *, log_prefix: str = "[Google Maps]") -> list[str]:
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print(f"{log_prefix} WARNING: GOOGLE_MAPS_API_KEY not found in environment.")
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
            print(f"{log_prefix} Place details returned status '{payload.get('status')}' for photo lookup")
            return []

        photos = payload.get("result", {}).get("photos") or []
        return [photo.get("photo_reference") for photo in photos if photo.get("photo_reference")]
    except Exception as error:
        print(f"{log_prefix} Error fetching photo references for '{place_id}': {error}")
        return []


def download_place_photo(photo_reference: str, *, name: str, log_prefix: str = "[Google Maps]") -> str | None:
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print(f"{log_prefix} WARNING: GOOGLE_MAPS_API_KEY not found in environment.")
        return None

    PHOTO_DIR.mkdir(parents=True, exist_ok=True)

    filename = f"{''.join(character.lower() if character.isalnum() else '-' for character in name)[:60].strip('-') or 'location'}_{uuid4().hex}.jpg"
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
        print(f"{log_prefix} Photo saved to {target_path}")
        return f"/location_photos/{target_path.name}"
    except Exception as error:
        print(f"{log_prefix} Error downloading photo for '{name}': {error}")
        return None