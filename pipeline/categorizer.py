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

    # Passiamo il testo originale a Spacy, altrimenti il NER perde precisione senza Maiuscole
    if _looks_like_address_query(text):
        return PlatformType.TEXT
    
    else:
        return PlatformType.UNKNOWN

def _looks_like_address_query(text: str) -> bool:
    """Valuta se il testo sembra un indirizzo o un luogo usando NLP ed euristiche."""
    
    lower_text = text.lower()
    
    # Se la query è ESATTAMENTE e SOLO una macro-metropoli (o varianti con numeri), la ignoriamo.
    # Evitiamo falsi positivi per frasi minime tipo "5 waggyu tokyo" o "Tokyo"
    if re.fullmatch(r"\W*(tokyo|kyoto|osaka)\W*", lower_text) or re.search(r"\b\d+\s+\w+\s+tokyo\b|\b\d+w-tokyo\b", lower_text):
        return False
        
    # Se contiene link non di Google Maps, scartalo
    if re.search(r"https?://(?!maps\.google\.com|maps\.app\.goo\.gl)", lower_text):
        return False
        
    # Per NLP, massimizzare il successo facendolo come Title Case (permette di trovare meglio FAC, LOC, GPE)
    # ma controlliamo anche il testo originale.
    doc = nlp(text.title())
    targets = {"GPE", "FAC", "LOC"}
    nlp_found = any(ent.label_ in targets for ent in doc.ents)
    
    # Geo-hints forti (sempre validi se presenti)
    strong_geo_hints = {"temple", "shrine", "museum", "park", "garden", "market", "station"}
    has_hints = any(term in lower_text for term in strong_geo_hints)
    has_ji = re.search(r"\b\w+(-?ji|-?tera)\b", lower_text)
    
    # NLP o indizi forti di posti
    if nlp_found or has_hints or has_ji:
        return True
        
    # Nomi di città specifici (spacy spesso li confonde per ORG come Kanazawa o Wakayama)
    known_jp_cities = {"kanazawa", "wakayama", "shibamata"}
    if any(city in lower_text for city in known_jp_cities):
        return True

    return False