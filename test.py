import asyncio
import requests
import re
from urllib.parse import urlparse, parse_qs
from pipeline.geocoder import GoogleMapsGeocoder

# I due messaggi da testare
message1 = "Ninenzaka - Kyoto\nhttps://maps.app.goo.gl/Y5SLYDjjvMJVEaq1A"
message2 = "https://maps.app.goo.gl/fZi74PpDFB2rvJCM7?g_st=ic"

def extract_url(text):
    """Estrae il link di Google Maps dal testo"""
    match = re.search(r'(https?://(?:www\.)?(?:maps\.app\.goo\.gl|goo\.gl/maps|maps\.google\.com|google\.com/maps)[^\s]+)', text)
    return match.group(1) if match else None

def resolve_short_url(url):
    """Espande il link corto"""
    if "maps.app.goo.gl" in url or "goo.gl" in url:
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.head(url, allow_redirects=True, headers=headers, timeout=5)
            return response.url
        except Exception as e:
            print(f"  Errore nel risolvere: {e}")
            return url
    return url

def extract_place_id(url):
    """Tenta di estrarre il place_id o ftid da un URL Google Maps"""
    # Cerca ftid nei parametri
    match = re.search(r'ftid=([^&]+)', url)
    if match:
        return match.group(1)
    
    # Cerca place_id nei parametri
    match = re.search(r'place_id=([^&]+)', url)
    if match:
        return match.group(1)
    
    # Cerca il format 0x....:0x.... che appare nel path di Google Maps
    match = re.search(r'0x[a-f0-9]+:0x[a-f0-9]+', url)
    if match:
        return match.group(0)
    
    return None

def extract_query_param(url):
    """Estrae il parametro 'q' o 'query' dall'URL"""
    parsed_url = urlparse(url)
    params = parse_qs(parsed_url.query)
    if 'q' in params:
        return params['q'][0]
    if 'query' in params:
        return params['query'][0]
    return None

async def test_message(name, message):
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")
    print(f"Messaggio originale:\n{message}\n")
    
    # 1. Estrai il link
    url = extract_url(message)
    print(f"1. Link estratto:\n   {url}\n")
    
    # 2. Risolvi il link corto
    long_url = resolve_short_url(url)
    print(f"2. URL risolto:\n   {long_url}\n")
    
    # 3. Tenta di estrarre il place_id
    place_id = extract_place_id(long_url)
    print(f"3. Place ID estratto:\n   {place_id if place_id else 'NESSUNO'}\n")
    
    # 4. Tenta di estrarre il parametro query
    query_param = extract_query_param(long_url)
    print(f"4. Query parameter estratto:\n   {query_param if query_param else 'NESSUNO'}\n")
    
    # 5. Tenta il geocoder
    print(f"5. Test del geocoder:")
    geocoder = GoogleMapsGeocoder()
    result = geocoder.resolve(long_url, download_n_images=0) # type: ignore
    if result:
        print(f"   ✓ Geocoder ha trovato: {result.get('name')}")
        print(f"     Lat: {result.get('lat')}, Lng: {result.get('lng')}")
    else:
        print(f"   ✗ Geocoder NON ha trovato nulla")
        
        # Prova fallback con il testo del messaggio
        print(f"\n6. Tentativo fallback con il testo del messaggio:")
        text_lines = message.split('\n')
        text_part = text_lines[0].strip() if text_lines else message
        print(f"   Testo usato: '{text_part}'")
        fallback_result = geocoder.search_by_text(text_part, download_n_images=0)
        if fallback_result:
            print(f"   ✓ Fallback ha trovato: {fallback_result.get('name')}")
            print(f"     Lat: {fallback_result.get('lat')}, Lng: {fallback_result.get('lng')}")
        else:
            print(f"   ✗ Fallback NON ha trovato nulla")

async def main():
    print("\n" + "="*60)
    print("ANALISI DELLE DIFFERENZE TRA I DUE LINK")
    print("="*60)
    
    await test_message("Messaggio 1 (SCARTATO)", message1)
    await test_message("Messaggio 2 (PROCESSATO)", message2)

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(main())