import json
import re
import requests
from typing import Any, Optional, cast

from data.database import Database
from models.instagram_reel import InstagramReel

from deep_translator import GoogleTranslator

db = Database("sqlite:///data/database.db")

def _parse_ai_response_json(content: str) -> Optional[Any]:
    try:
        return json.loads(content)
    except Exception:
        pass

    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
    if fenced:
        snippet = fenced.group(1).strip()
        try:
            return json.loads(snippet)
        except Exception:
            pass

    bracket_start = min(
        [idx for idx in [content.find("["), content.find("{")] if idx != -1] or [-1]
    )
    if bracket_start >= 0:
        snippet = content[bracket_start:].strip()
        for end in range(len(snippet), 1, -1):
            chunk = snippet[:end]
            try:
                return json.loads(chunk)
            except Exception:
                continue

    return None

def _extract_all_json_values(content: str) -> list[Any]:
    decoder = json.JSONDecoder()
    values: list[Any] = []
    i = 0
    n = len(content)

    while i < n:
        ch = content[i]
        if ch not in "[{":
            i += 1
            continue

        try:
            obj, end = decoder.raw_decode(content, i)
            values.append(obj)
            i = end
        except Exception:
            i += 1

    return values


def _translate_to_english_if_needed(text: str) -> str:
   
    if not text.strip():
        return text
    
    try:
        print("[AI Extractor Worker] Checking language and translating via Google Translate if not English...")
        translated = GoogleTranslator(source='auto', target='en').translate(text)
        if translated:
            return translated
        return text
    except Exception as e:
        print(f"[AI Extractor Worker] Error during Google Translate: {e}")
        
    return text


if __name__ == "__main__":
    reels = db.get_reels_by_pipeline_status("pending_ai")

    if not reels:
        print("No reel found with the specified Telegram ID.")
        exit(0)
    
    for reel in reels:
        reel = cast(InstagramReel, reel)

        print(f"[AI Extractor Worker] Processing reel: {reel.shortcode}")
        
        description_for_prompt = (reel.description or "").strip()
        ocr_for_prompt = (reel.ocr_text or "").strip()

        combined_text = f"Description in video description:\n{description_for_prompt}".strip()
        
        if ocr_for_prompt:
            combined_text = (f"{combined_text}\n\n" "OCR text extracted from burned-in subtitles in the video (some l are !):\n" f"{ocr_for_prompt}").strip()

        combined_text = _translate_to_english_if_needed(combined_text)

        system_prompt = (
            "You are an expert travel information extractor.\n"
            "You extract real-world visitable places from informal travel content.\n"
            "Return STRICT JSON only. No explanations."
        )

        task_prompt = (
            "Extract real-world places (restaurants, landmarks, cities, etc.) from the text.\n\n"

            "CRITICAL:\n"
            "- Extract ONLY actual physical places that people can visit\n"
            "- Do NOT extract concepts, foods, dishes, or menu items\n"
            "- Do NOT extract brand names unless they clearly refer to a real place\n"
            "- Do NOT return empty results if at least one valid place exists\n\n"

            "STRICT PLACE DEFINITION:\n"
            "A valid place MUST be a physical location that exists on a map.\n\n"

            "DO NOT EXTRACT:\n"
            "- Food names (e.g. Wagyu, Kimchi)\n"
            "- Menu items or dishes (e.g. 'Mom’s Kimchi')\n"
            "- Ingredients\n"
            "- Vibes, styles, or concepts (e.g. 'Osaka street-style')\n"
            "- Generic areas unless clearly a destination\n\n"

            "BUSINESS DETECTION RULES:\n"
            "- Extract restaurant names when clearly presented as a place\n"
            "- Phrases like 'That is X', 'We are X' indicate a business\n"
            "- If a name represents the establishment, include it\n\n"

            "LOCATION CONTEXT RULES:\n"
            "- Use hashtags (e.g. #osakafood) to infer city\n"
            "- DO NOT extract the city itself unless it is a main destination\n"
            "- DO NOT duplicate context locations as results\n\n"

            "AREA HANDLING:\n"
            "- Areas like 'Namba' should only be included if they are a destination in the story\n"
            "- If used only as context (hashtags, vague mention), IGNORE\n\n"

            "INFERENCE RULES:\n"
            "- If a restaurant name is present, include it even without address\n"
            "- Infer city and country from context\n"
            "- Prefer one strong correct place over many weak ones\n\n"

            "OUTPUT RULES:\n"
            "- Avoid duplicates\n"
            "- Keep output minimal and precise\n"
            "- Typically 1–3 places per short text\n\n"

            "Return a JSON array with this schema:\n"
            "{\n"
            '  "name": string,\n'
            '  "normalized_name": string,\n'
            '  "category": one of [food, landmark, fun, culture, transport, city, other],\n'
            '  "city": string,\n'
            '  "country": string,\n'
            '  "address": string or null,\n'
            '  "google_maps_query": string,\n'
            '  "confidence": number (0-1),\n'
            '  "evidence_text": string\n'
            "}\n\n"

            "GOOD EXAMPLE:\n"
            "Text: That is Yakiniku Matsumoto #osakafood\n"
            "Output:\n"
            "[{\n"
            '  "name": "Yakiniku Matsumoto",\n'
            '  "normalized_name": "Yakiniku Matsumoto",\n'
            '  "category": "food",\n'
            '  "city": "Osaka",\n'
            '  "country": "Japan",\n'
            '  "address": null,\n'
            '  "google_maps_query": "Yakiniku Matsumoto Osaka Japan",\n'
            '  "confidence": 0.7,\n'
            '  "evidence_text": "That is Yakiniku Matsumoto"\n'
            "}]\n\n"

            "BAD EXAMPLES (DO NOT DO THIS):\n"
            "- Wagyu → NOT a place\n"
            "- Mom’s Kimchi → NOT a place\n"
            "- Osaka → context only\n"
            "- Namba → context only\n\n"

            "Return ONLY valid JSON.\n\n"

            "Text:\n"
            f"{combined_text}\n"
        )
        # ollama_model = "qwen2.5:7b-instruct"
        ollama_model = "qwen2.5:14b"
        # ollama_model = "llama-3.1-8B-Instruct"
        # ollama_model = "gemma4:latest"
        # ollama_model = "qwen3.5:9b"
        ollama_url = "http://localhost:11434/api/chat"
        ai_temperature = 0.1
        ai_top_p = 0.9
        ai_repeat_penalty = 1.1
        ai_num_ctx = 8192
        ai_force_json_mode = False
        ai_wrapper_key = ""

        payload = {
            "model": ollama_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": ai_temperature,
                "top_p": ai_top_p,
                "repeat_penalty": ai_repeat_penalty,
                "num_ctx": ai_num_ctx
            }
        }
    
        if ai_force_json_mode:
            payload["format"] = "json"

        try:
            response = requests.post(ollama_url, json=payload, timeout=520)
            response.raise_for_status()

            content = (response.json().get("message") or {}).get("content") or "[]"

            parsed = _parse_ai_response_json(content)
            
            if parsed is None:
                all_values = _extract_all_json_values(content)
                if len(all_values) == 1:
                    parsed = all_values[0]
                elif len(all_values) > 1:
                    merged: list[Any] = []
                    for value in all_values:
                        if isinstance(value, list):
                            merged.extend(value)
                        else:
                            merged.append(value)
                    parsed = merged

            if isinstance(parsed, dict):
                if ai_wrapper_key:
                    parsed = parsed.get(ai_wrapper_key, [])
                else:
                    wrapped = parsed.get("places") or parsed.get("items")
                    if isinstance(wrapped, list):
                        parsed = wrapped
                    elif isinstance(wrapped, dict):
                        parsed = [wrapped]
                    elif parsed.get("name"):
                        parsed = [parsed]
                    else:
                        parsed = []
            elif not isinstance(parsed, list):
                parsed = []

            cleaned: list[dict[str, Any]] = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                name = (item.get("name") or "").strip()
                if not name:
                    continue

                try:
                    confidence = float(item.get("confidence", 0.0))
                except (TypeError, ValueError):
                    confidence = 0.0

                city = (item.get("city") or "").strip()
                google_maps_query = (item.get("google_maps_query") or "").strip()
                if not google_maps_query:
                    google_maps_query = " ".join(part for part in [name, city] if part).strip()
                
                place_data = {
                    "name": name,
                    "description": (item.get("description") or "").strip(),
                    "category": (item.get("category") or "other").strip().lower(),
                    "city": city,
                    "google_maps_query": google_maps_query,
                    "confidence": max(0.0, min(1.0, confidence)),
                    "evidence_text": (item.get("evidence_text") or "").strip(),
                }
                cleaned.append(place_data)

            place_count = len(cleaned)
            reel.ai_source = "description+ocr" if ocr_for_prompt else "description"
            reel.ai_status = "success" if place_count > 0 else "no_places"
            reel.ai_places_json = cleaned
            reel.pipeline_status = "pending_maps"

            print("\n\n[AI Extractor Worker] AI extraction result:")
            print(json.dumps(cleaned, indent=2, ensure_ascii=False))
            
            db.upsert_instagram_reel(reel)
            print(f"[AI Extractor Worker] AI extraction saved ({reel.ai_status}, {place_count} places). Moving to pending_maps.")
            
        except Exception as e:
            print(f"[AI Extractor Worker] Error processing AI: {e}")
