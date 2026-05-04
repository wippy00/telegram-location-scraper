from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from data.database import Database


def resolve_telegram_id(db: Database, location) -> int | None:
    if location.telegram_message_id is not None:
        return location.telegram_message_id

    source_url = (location.source_url or "").strip()
    if source_url.startswith("telegram:"):
        try:
            return int(source_url.split(":", 1)[1])
        except (IndexError, ValueError):
            return None

    if source_url:
        reel = db.get_instagram_reel_by_source_url(source_url)
        if reel is not None:
            return reel.telegram_id

    return None


def main() -> int:
    db = Database()
    locations = db.get_locations()

    updated = 0
    skipped = 0
    unresolved = 0

    for location in locations.values():
        telegram_id = resolve_telegram_id(db, location)

        if telegram_id is None:
            unresolved += 1
            print(f"[Backfill] Skipped {location.id}: no Telegram reference found")
            continue

        if location.telegram_message_id == telegram_id:
            skipped += 1
            continue

        location.telegram_message_id = telegram_id
        db.update_location(location)
        updated += 1
        print(f"[Backfill] Updated {location.id} -> telegram_message_id={telegram_id}")

    print(
        f"[Backfill] Done. updated={updated} skipped={skipped} unresolved={unresolved} total={len(locations)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())