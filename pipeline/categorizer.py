import re
import spacy
from models import PlatformType

# Inizializza spacy
nlp = spacy.load("en_core_web_sm")

def categorize_message(text: str) -> PlatformType:
    lower_text = text.lower()

    if "instagram.com/reel/" in lower_text or "instagram.com/p/" in lower_text:
        return PlatformType.INSTAGRAM
    
    if any(m in lower_text for m in ["maps.google.com", "goo.gl/maps", "maps.app.goo.gl"]):
        return PlatformType.GOOGLE_MAPS

    if _looks_like_address_query(text):
        return PlatformType.TEXT
    
    else:
        return PlatformType.UNKNOWN

def _looks_like_address_query(text: str) -> bool:
    """Valuta se il testo sembra un indirizzo o un luogo d'interesse (POI)."""
    
    lower_text = text.lower().strip()

    # 1. Escludi link: se stai cercando messaggi di testo puro, ignora i link
    if "http://" in lower_text or "https://" in lower_text:
        return False

    # 2. REGOLE FORTI (Se matchano, è quasi sicuramente un indirizzo)
    strong_address_patterns = [
        r'〒\s*\d{3}-\d{4}',            # Simbolo postale giapponese + CAP (es. 〒160-0021)
        r'\b\d{3}-\d{4}\b',           # Solo CAP giapponese (es. 562-8508)
        r'\d+\s*chome(-\d+)*',        # Formato vie/isolati (es. 1 Chome-12-16)
        r'\b\w+\s+(city|ku|shi|ken)\b' # Formato prefetture/quartieri (es. Minato City, Shinjuku-ku)
    ]
    
    if any(re.search(pat, lower_text) for pat in strong_address_patterns):
        return True

    # 3. REGOLE PER PUNTI DI INTERESSE (POI) E RICERCHE SECCHE
    # Chi cerca un luogo di solito scrive poche parole (es. "nara deer park")
    words = lower_text.split()
    
    # Se il testo è troppo lungo, quasi sicuramente è una conversazione
    if len(words) > 10:
        return False

    # Parole che indicano un luogo turistico/POI in inglese/romaji
    poi_keywords = ['temple', 'park', 'market', 'shrine', 'station', 'gym', 'village', 'ji', 'dera', 'museum']
    cities = ['tokyo', 'kyoto', 'osaka', 'kanazawa', 'nara', 'kamakura', 'nikko', 'kobe', 'wakayama', 'akihabara']
    
    has_poi = any(poi in lower_text for poi in poi_keywords)
    has_city = any(city in lower_text for city in cities)

    # Se ha un POI (es. "hitachi seaside park"), lo consideriamo buono
    if has_poi:
        return True

    # Se menziona solo una città (es. "Kanazawa..." o "da tokyo...") 
    # filtriamo usando le stop-words italiane. Se ha articoli/preposizioni, è una conversazione.
    if has_city and len(words) <= 5:
        italian_stop_words = {'da', 'a', 'in', 'di', 'il', 'la', 'un', 'una', 'e', 'ma', 'se', 'per'}
        message_words = set(words)
        
        # Se NON ci sono parole colloquiali italiane, considerala una ricerca (es. "kanazawa", "5 waggyu tokyo")
        if message_words.isdisjoint(italian_stop_words):
            return True

    return False