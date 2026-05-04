import os
import json
import re
import requests
from typing import Any, Optional, cast

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data.database import Database
from models.instagram_reel import InstagramReel

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

        system_prompt = (
            "You are an expert travel information extractor.\n"
            "You extract real-world visitable places from informal travel content.\n"
            "You are highly skilled at inferring likely place names from descriptions.\n"
            "Return STRICT JSON only. No explanations."
        )

        task_prompt = (
            "Extract all real-world places (landmarks, cities, transport hubs, beaches, temples, shrines, viewpoints, restaurants, etc.).\n"
            "Use BOTH the description and OCR text. OCR may contain errors (e.g. '!' instead of 'l'). Fix them when obvious.\n\n"

            "CRITICAL:\n"
            "- Extract ONLY places that are actual VISITED locations or meaningful destinations in the context\n"
            "- Do NOT extract places that are only mentioned as directions, references, or proximity (e.g. '5 mins from Shinjuku')\n"
            "- Do NOT extract places that are only used as orientation or meeting points unless they are a real stop in the journey\n"
            "- Do NOT stop early; continue until all relevant places are found\n"
            "- If the text is short, it's OK to return only 1–2 places\n"
            "- If it's a travel itinerary, multiple places are expected\n"
            "- You will be penalized if you include irrelevant places\n\n"

            "PROCESS:\n"
            "- First identify ALL place mentions or hints (including vague descriptions)\n"
            "- Then filter only the places that are actual destinations or visited spots\n\n"

            "IMPORTANT:\n"
            "- Include BOTH explicitly mentioned places AND inferred places\n"
            "- Also extract major landmarks like Mt. Fuji if clearly referenced\n"
            "- If a place is described but not named, infer the MOST LIKELY real-world place\n"
            "- Prefer SPECIFIC places over generic descriptions\n\n"

            "INFERENCE RULES:\n"
            "- Match descriptions to real known locations in that area\n"
            "- Use strong priors (famous temples, shrines, landmarks, popular spots)\n"
            "- When a temple or shrine is described, try to match it to a known real location\n"
            "- Do NOT invent place names\n"
            "- Avoid generic names like 'Tateyama Temple'\n"
            "- If unsure, choose the most likely real place and lower confidence\n"
            "- If multiple matches are possible, pick the most famous/relevant one\n\n"

            "FILTERING RULES (VERY IMPORTANT):\n"
            "- DO NOT include transport references unless they are actual stops (e.g. stations used as destinations)\n"
            "- DO NOT include places mentioned only as directions or navigation (e.g. '5 mins from X', 'near X')\n"
            "- DO NOT include context locations unless they are explicitly visited or part of the itinerary\n"
            "- Example: 'Shinjuku, 5 mins walk' → DO NOT extract Shinjuku Station\n"
            "- Example: 'we visited Shinjuku Station' → OK\n\n"

            "CONTEXT HANDLING:\n"
            "- Identify the MAIN CONTEXT location of the text\n"
            "- Do NOT include the main context city as a separate extracted place unless explicitly visited as a destination\n\n"

            "Extraction scope:\n"
            "- Cities and regions\n"
            "- Landmarks (mountains, beaches, viewpoints)\n"
            "- Temples and shrines\n"
            "- Transport locations (ONLY if actual stops or visited places)\n"
            "- Notable tourist spots\n\n"

            "Rules:\n"
            "- Only include places that can be searched on Google Maps\n"
            "- Normalize names (fix casing, spacing, typos)\n"
            "- Avoid duplicates\n"
            "- Regions, peninsulas, and large areas are 'landmark', NOT 'city'\n"
            "- City and country MUST NOT be empty; infer them if missing\n"
            "- Do NOT include duplicate or redundant places\n\n"

            "For inferred places:\n"
            "- Use real known locations that best match the description\n"
            "- Base inference on context (city, region, clues in text)\n\n"

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

            "The field 'google_maps_query' MUST be a clean search query combining name + location.\n"
            "Example: 'Awa Shrine Tateyama Chiba Japan'\n\n"

            "Confidence guidelines:\n"
            "- 0.9–1.0: explicitly mentioned\n"
            "- 0.7–0.9: strongly implied\n"
            "- 0.4–0.7: reasonable inference\n\n"

            "Example 1:\n"
            "Text: A famous red temple in Kyoto with many torii gates\n"
            "Output:\n"
            "[{\n"
            '  "name": "Fushimi Inari Taisha",\n'
            '  "normalized_name": "Fushimi Inari Taisha",\n'
            '  "category": "culture",\n'
            '  "city": "Kyoto",\n'
            '  "country": "Japan",\n'
            '  "address": null,\n'
            '  "google_maps_query": "Fushimi Inari Taisha Kyoto Japan",\n'
            '  "confidence": 0.8,\n'
            '  "evidence_text": "red temple with many torii gates"\n'
            "}]\n\n"

            "Example 2:\n"
            "Text: A shrine near Tateyama with a torii gate facing Mt Fuji\n"
            "Output:\n"
            "[{\n"
            '  "name": "Awa Shrine",\n'
            '  "normalized_name": "Awa Shrine",\n'
            '  "category": "culture",\n'
            '  "city": "Tateyama",\n'
            '  "country": "Japan",\n'
            '  "address": null,\n'
            '  "google_maps_query": "Awa Shrine Tateyama Chiba Japan",\n'
            '  "confidence": 0.75,\n'
            '  "evidence_text": "shrine with torii gate facing Mt Fuji"\n'
            "}]\n\n"

            "Return ONLY a valid JSON array.\n"
            "Ensure the JSON is complete and properly formatted.\n"
            "Do not omit closing brackets.\n"
            "Do not include any text outside JSON.\n\n"

            "Text:\n"
            f"{combined_text}\n"
        )
        ollama_model = "qwen2.5:7b-instruct"
        # ollama_model = "qwen2.5:14b"
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
            # payload["format"] = {
            #     "type": "json_schema",
            #     "json_schema": {
            #         "name": "places_extraction",
            #         "schema": {
            #             "type": "array",
            #             "items": {
            #                 "type": "object",
            #                 "properties": {
            #                     "name": {"type": "string"},
            #                     "normalized_name": {"type": "string"},
            #                     "category": {"type": "string"},
            #                     "city": {"type": "string"},
            #                     "country": {"type": "string"},
            #                     "address": {"type": ["string", "null"]},
            #                     "google_maps_query": {"type": "string"},
            #                     "confidence": {"type": "number"},
            #                     "evidence_text": {"type": "string"}
            #                 },
            #                 "required": [
            #                     "name",
            #                     "normalized_name",
            #                     "category",
            #                     "city",
            #                     "country",
            #                     "google_maps_query",
            #                     "confidence",
            #                     "evidence_text"
            #                 ]
            #             }
            #         }
            #     }
            # }

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

                google_maps_query = (item.get("google_maps_query") or "").strip()
                
                place_data = {
                    "name": name,
                    "normalized_name": (item.get("normalized_name") or name).strip(),
                    "category": (item.get("category") or "other").strip().lower(),
                    "city": (item.get("city") or "").strip(),
                    "country": (item.get("country") or "").strip(),
                    "address": (item.get("address") or "").strip() if item.get("address") else None,
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
