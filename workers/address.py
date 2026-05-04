from uuid import uuid4

from data.database import Database
from models.location import Location, MarkerCategory
from workers.google_maps_common import (
    download_place_photo,
    fetch_place_photo_references,
    make_location_checksum,
    search_place,
)

db = Database("sqlite:///data/database.db")


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
        checksum = make_location_checksum(name, lat, lng)
        photo_paths = []

        photo_references = result.get("photo_references") or []
        if not photo_references and result.get("place_id"):
            photo_references = fetch_place_photo_references(result["place_id"], log_prefix="[Address Worker]")

        for photo_reference in photo_references[:3]:
            photo_path = download_place_photo(photo_reference, name=name, log_prefix="[Address Worker]")
            if photo_path:
                photo_paths.append(photo_path)

        if not db.get_location_by_checksum(checksum):
            location = Location(
                id=uuid4().hex,
                name=name,
                lat=lat,
                lng=lng,
                telegram_message_id=message.telegram_id,
                description=query,
                google_maps_url=result["google_maps_url"],
                photo_paths=photo_paths or None,
                source_url=f"telegram:{message.telegram_id}",
                category=_infer_location_category(query),
                checksum=checksum,
                platform="address",
            )
            db.insert_location(location)
            added_locations += 1

        db.update_message_status(message.telegram_id, "done", category="address")

    print(f"[Address Worker] Done. Added {added_locations} new location(s).")
