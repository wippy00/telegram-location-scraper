import re
from models import PlatformType

def categorize_message(text: str) -> PlatformType:
    lower_text = text.lower()

    if "instagram.com/reel/" in lower_text or "instagram.com/p/" in lower_text:
        return PlatformType.INSTAGRAM
    
    if any(m in lower_text for m in ["maps.google.com", "goo.gl/maps", "maps.app.goo.gl"]):
        return PlatformType.GOOGLE_MAPS

    if _looks_like_address_query(lower_text):
        return PlatformType.TEXT
    
    return PlatformType.UNKNOWN

def _looks_like_address_query(text: str) -> bool:
    # (Mantieni qui la tua logica di regex originale)
    if re.search(r"\b\d+\s*chome-\d+(?:-\d+){1,2}\b", text): return True
    if re.search(r"\b\d{3}-\d{4}\b", text): return True
    if re.search(r"\b[a-z]+\s+city\b", text): return True
    
    geo_hints = ["tokyo", "kyoto", "osaka", "kamakura", "kanagawa", "station", "temple", "shrine", "museum", "park", "garden"]
    if any(term in text for term in geo_hints): return True

    words = re.findall(r"[a-z0-9]+", text)
    if 1 <= len(words) <= 3:
        chat_words = {"fast", "food", "cibo", "italia", "japan", "giappone"} # ... resto della tua lista
        if not any(w in chat_words for w in words): return True
    return False