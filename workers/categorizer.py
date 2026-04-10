import re

from data.database import Database

db = Database("sqlite:///data/database.db")


def _is_generic_link(text: str) -> bool:
    if "http://" not in text and "https://" not in text:
        return False
    return not any(domain in text for domain in ["instagram.com", "maps.google.com", "goo.gl/maps", "maps.app.goo.gl"])


def _looks_like_address_query(text: str) -> bool:
    # Explicit address formats (street blocks, Japanese ZIP, city syntax)
    if re.search(r"\b\d+\s*chome-\d+(?:-\d+){1,2}\b", text):
        return True
    if re.search(r"\b\d{3}-\d{4}\b", text):
        return True
    if re.search(r"\b[a-z]+\s+city\b", text):
        return True

    # Intent phrases for places (e.g. "passiamo a Shibamata")
    if re.search(r"\b(passiamo|andiamo|andare|visitare|vedere)\s+a\s+\w+", text):
        return True

    # Place + context hints (very strong indicators)
    geo_hints = ["tokyo", "kyoto", "osaka", "kamakura", "kanagawa", "station", "temple", "shrine", "museum", "park", "garden", "kokedera"]
    if any(term in text for term in geo_hints):
        return True

    # Very short query-like text is often a place search (e.g. "Kanazawa")
    # We must filter out common Italian conversational words, verbs, and slang
    words = re.findall(r"[a-z0-9]+", text)
    if 1 <= len(words) <= 3:
        chat_words = {
            "fast", "food", "cibo", "ragazzi", "italia", "japan", "giappone",
            "il", "lo", "la", "i", "gli", "le", "un", "una", "uno", 
            "di", "a", "da", "in", "con", "su", "per", "tra", "fra",
            "che", "non", "si", "no", "mi", "ti", "ci", "vi", "ai",
            "odio", "morte", "apposto", "tassativo", "que", "rifiuto", 
            "mandero", "sogno", "anguilla", "tiktok", "negri"
        }
        if not any(w in chat_words for w in words):
            return True

    return False

if __name__ == "__main__":
    messages = db.get_messages_without_category()
    messages.extend(db.get_messages_by_category("random"))
    messages.extend(db.get_messages_by_category("address"))

    seen_telegram_ids = set()
    for message in messages:
        if message.telegram_id in seen_telegram_ids:
            continue
        seen_telegram_ids.add(message.telegram_id)

        raw_text = message.raw_text or ""
        lower_text = raw_text.lower()
        category = "random"

        if "instagram.com/reel/" in lower_text or "instagram.com/p/" in lower_text:
            category = "instagram"

        elif "maps.google.com" in lower_text or "goo.gl/maps" in lower_text or "maps.app.goo.gl" in lower_text:
            category = "maps"

        elif _is_generic_link(lower_text):
            category = "random"

        elif "fast food" in lower_text:
            category = "random"

        elif _looks_like_address_query(lower_text):
            category = "address"

        elif "chrome" in lower_text:
            category = "chrome"

        preview = raw_text[:50].encode("ascii", errors="replace").decode("ascii")
        print("[Categoryzer]", category, "\n", preview, "\n\n")

        db.update_message_status(message.telegram_id, "categorized", category=category)