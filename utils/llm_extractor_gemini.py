"""
Extractor for travel places using Google Gemini 3.1 Flash API.
Replaces the local Ollama-based llm_extractor.py with a cloud-based solution.

Features:
- Uses Google Gemini 3.1 Flash (free tier available)
- Supports video analysis (OCR + LLM extraction in one call)
- Same interface as the original llm_extractor
- Handles JSON parsing and cleanup

Requirements:
- pip install google-genai python-dotenv
- Set GEMINI_API_KEY environment variable
"""

import os
import json
import re
import time
from typing import Any, Optional
from google import genai
from google.genai import types
from deep_translator import GoogleTranslator


def _parse_ai_response_json(content: str) -> Optional[Any]:
    """Parse JSON from AI response, handling various formats."""
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

    bracket_start = min([idx for idx in [content.find("["), content.find("{")] if idx != -1] or [-1])
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
    """Extract all JSON objects/arrays from text."""
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
    """Translate text to English if needed."""
    if not text.strip():
        return text
    try:
        print("[AI Extractor] Checking language and translating via Google Translate if not English...")
        translated = GoogleTranslator(source='auto', target='en').translate(text)
        if translated:
            return translated
        return text
    except Exception as e:
        print(f"[AI Extractor] Error during Google Translate: {e}")
    return text


def extract_places_from_video(video_path: str, description: str) -> list[dict[str, Any]]:
    """
    Extract travel places directly from video + description using Google Gemini multimodal.
    Gemini reads the video (OCR + visual analysis) + description in ONE call.
    Much faster and smarter than doing OCR separately.
    
    Args:
        video_path: Path to the video file (MP4, etc.)
        description: Video description or post text
        
    Returns:
        List of place dictionaries (same format as extract_places_via_llm)
    """
    
    if not os.path.exists(video_path):
        print(f"[AI Extractor] Error: Video file not found: {video_path}")
        return []
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[AI Extractor] Error: GEMINI_API_KEY environment variable not set")
        return []
    
    client = genai.Client(api_key=api_key)
    
    description = _translate_to_english_if_needed(description)

    system_prompt = (
        "You are an expert travel information extractor.\n"
        "You watch videos, read text from burned-in subtitles AND descriptions.\n"
        "You extract real-world visitable places from the video and text content.\n"
        "Return STRICT JSON only. No explanations."
    )

    task_prompt = (
        "Watch this video carefully. Read all text overlays, subtitles, signage visible in the video.\n"
        "Then read the description provided.\n"
        "Extract real-world places (restaurants, landmarks, cities, temples, beaches, etc.) from BOTH sources.\n\n"
        "CRITICAL:\n"
        "- Extract ONLY actual physical places that people can visit\n"
        "- Do NOT extract concepts, foods, dishes, or menu items\n"
        "- Do NOT extract brand names unless they clearly refer to a real place\n"
        "- Do NOT return empty results if at least one valid place exists\n\n"
        "STRICT PLACE DEFINITION:\n"
        "A valid place MUST be a physical location that exists on a map/real world. "
        "EVEN IF they do not say the EXACT NAME of the place (e.g. '8th century temple' or 'shrine with Mt. Fuji view' MUST be extracted as places!).\n\n"
        "DO NOT EXTRACT:\n"
        "- Food names (e.g. Wagyu, Kimchi)\n"
        "- Menu items or dishes (e.g. 'Mom's Kimchi')\n"
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
        "- If a point of interest or temple or shop is described but without its specific proper name, "
        "extract it using the descriptive name provided (e.g. 'Stunning shrine with Mt Fuji views', 'ocean pier').\n"
        "- Infer city and country from context\n"
        "- Prefer one strong correct place over many weak ones\n\n"
        "OUTPUT RULES:\n"
        "- EXTRACT EVERY SINGLE STOP/ATTRACTION MENTIONED IN A TOUR/DAY TRIP.\n"
        "- Avoid duplicates\n"
        "- Keep output precise\n\n"
        "Return a JSON array with this schema:\n"
        "[\n"
        "  {\n"
        '    "name": "string",\n'
        '    "description": "string",\n'
        '    "normalized_name": "string",\n'
        '    "category": "one of [food, landmark, fun, culture, transport, city, other]",\n'
        '    "city": "string",\n'
        '    "country": "string",\n'
        '    "address": "string or null",\n'
        '    "google_maps_query": "string",\n'
        '    "confidence": "number (0-1)",\n'
        '    "evidence_text": "string"\n'
        "  }\n"
        "]\n\n"
        "Return ONLY valid JSON."
    )

    try:
        print(f"[AI Extractor] Uploading video for multimodal analysis: {video_path}...")
        video_file = client.files.upload(file=video_path)
        
        print("[AI Extractor] Waiting for video processing...")
        while video_file.state == "PROCESSING":
            print(".", end="", flush=True)
            time.sleep(2)
            video_file = client.files.get(name=video_file.name) # type: ignore
        print(" Done!")
        
        if video_file.state == "FAILED":
            print("[AI Extractor] Error: Video processing failed on Google servers")
            return []

        print("[AI Extractor] Sending to Gemini for analysis...")
        response = client.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=[
                video_file,
                system_prompt,
                task_prompt,
                f"Description text:\n{description}"
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )

        # Cleanup: delete video from server
        print("[AI Extractor] Cleaning up (deleting video from server)...")
        client.files.delete(name=video_file.name) # type: ignore

        content = response.text or "[]"
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

            cleaned.append({
                "name": name,
                "description": (item.get("description") or "").strip(),
                "normalized_name": (item.get("normalized_name") or name).strip(),
                "category": (item.get("category") or "other").strip().lower(),
                "city": city,
                "country": (item.get("country") or "").strip(),
                "address": (item.get("address") or None),
                "google_maps_query": google_maps_query,
                "confidence": max(0.0, min(1.0, confidence)),
                "evidence_text": (item.get("evidence_text") or "").strip(),
            })

        return cleaned

    except Exception as e:
        print(f"[AI Extractor] Error in video analysis: {e}")
        return []


def extract_places_via_llm(description: str, ocr_text: str | None = None) -> list[dict[str, Any]]:
    """
    Extract travel places from description and OCR text using Google Gemini.
    
    Args:
        description: Video description or post text
        ocr_text: Optional OCR text extracted from video frames
        
    Returns:
        List of place dictionaries with keys:
        - name: Place name
        - description: Place description
        - normalized_name: Normalized name
        - category: One of [food, landmark, fun, culture, transport, city, other]
        - city: City name
        - country: Country name
        - address: Address or null
        - google_maps_query: Search query for Google Maps
        - confidence: Confidence score (0-1)
        - evidence_text: Quote from source text
    """
    
    # Initialize Gemini client
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[AI Extractor] Error: GEMINI_API_KEY environment variable not set")
        return []
    
    client = genai.Client(api_key=api_key)
    
    # Combine description and OCR text
    combined_text = f"Description in video description:\n{description}".strip()
    if ocr_text:
        combined_text = (
            f"{combined_text}\n\n"
            "OCR text extracted from burned-in subtitles in the video (some l are !):\n"
            f"{ocr_text}"
        ).strip()

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
        "A valid place MUST be a physical location that exists on a map/real world. "
        "EVEN IF they do not say the EXACT NAME of the place (e.g. '8th century temple' or 'shrine with Mt. Fuji view' MUST be extracted as places!).\n\n"
        "DO NOT EXTRACT:\n"
        "- Food names (e.g. Wagyu, Kimchi)\n"
        "- Menu items or dishes (e.g. 'Mom's Kimchi')\n"
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
        "- If a point of interest or temple or shop is described but without its specific proper name, "
        "extract it using the descriptive name provided (e.g. 'Stunning shrine with Mt Fuji views', 'ocean pier').\n"
        "- Infer city and country from context\n"
        "- Prefer one strong correct place over many weak ones\n\n"
        "OUTPUT RULES:\n"
        "- EXTRACT EVERY SINGLE STOP/ATTRACTION MENTIONED IN A TOUR/DAY TRIP.\n"
        "- Avoid duplicates\n"
        "- Keep output precise\n\n"
        "Return a JSON array with this schema:\n"
        "[\n"
        "  {\n"
        '    "name": "string",\n'
        '    "description": "string",\n'
        '    "normalized_name": "string",\n'
        '    "category": "one of [food, landmark, fun, culture, transport, city, other]",\n'
        '    "city": "string",\n'
        '    "country": "string",\n'
        '    "address": "string or null",\n'
        '    "google_maps_query": "string",\n'
        '    "confidence": "number (0-1)",\n'
        '    "evidence_text": "string"\n'
        "  }\n"
        "]\n\n"
        "Return ONLY valid JSON."
        "\n\nText:\n"
        f"{combined_text}\n"
    )

    try:
        print("[AI Extractor] Sending request to Google Gemini...")
        response = client.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=[system_prompt, task_prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )

        content = response.text or "[]"
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

            cleaned.append({
                "name": name,
                "description": (item.get("description") or "").strip(),
                "normalized_name": (item.get("normalized_name") or name).strip(),
                "category": (item.get("category") or "other").strip().lower(),
                "city": city,
                "country": (item.get("country") or "").strip(),
                "address": (item.get("address") or None),
                "google_maps_query": google_maps_query,
                "confidence": max(0.0, min(1.0, confidence)),
                "evidence_text": (item.get("evidence_text") or "").strip(),
            })

        return cleaned

    except Exception as e:
        print(f"[AI Extractor Worker] Error processing AI: {e}")
        return []
