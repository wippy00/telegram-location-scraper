import os
import re

def extract_burned_subtitles_text(
    video_path: str,
    sample_every_seconds: float = 1.0,
    max_frames: int = 80,
) -> tuple[str | None, str]:
    try:
        import cv2
        import numpy as np
        import easyocr
        from difflib import SequenceMatcher
    except ImportError:
        return None, "unavailable_missing_dependency"

    if not os.path.exists(video_path):
        return None, "unavailable_video_not_found"

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None, "unavailable_video_open_failed"

    BLACKLIST = {"power", "password", "top", "menu", "app", "battery", "wifi", "edition", "advisor"}
    SIMILARITY_THRESHOLD = 0.7 

    def similarity(a, b):
        return SequenceMatcher(None, a, b).ratio()

    def clean_text(text):
        t = re.sub(r'^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$', '', text)
        t = re.sub(r'[^a-zA-Z0-9\s]', ' ', t)
        t = " ".join(t.split())
        return t

    def is_junk(text, prob):
        t_low = text.lower().strip()
        if any(word in t_low for word in BLACKLIST): return True
        if len(text) < 3: return True
        if not re.search(r'[aeiouAEIOU]', text) and len(text) > 3: return True
        return False

    try:
        reader = easyocr.Reader(["en"], gpu=False)

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_step = max(1, int(fps * sample_every_seconds)) if fps > 0 else 30
        frame_index = 0
        sampled = 0

        last_full_lines = []
        all_captured_lines = []

        while sampled < max_frames:
            ok, frame = cap.read()
            if not ok:
                break

            if frame_index % frame_step != 0:
                frame_index += 1
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            denoised = cv2.medianBlur(gray, 3)
            upscaled = cv2.resize(denoised, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            kernel_sharpening = np.array([[-1,-1,-1], [-1, 9,-1], [-1,-1,-1]])
            sharpened = cv2.filter2D(upscaled, -1, kernel_sharpening)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            enhanced = clahe.apply(sharpened)

            results = reader.readtext(enhanced)

            valid_fragments = []
            for (bbox, text, prob) in results:
                cleaned = clean_text(text)
                if prob >= 0.5 and not is_junk(cleaned, prob): # type: ignore
                    valid_fragments.append({
                        'text': cleaned,
                        'x': bbox[0][0],
                        'y': bbox[0][1]
                    })

            valid_fragments.sort(key=lambda b: (b['y'] // 20, b['x']))
            full_line = " ".join([f['text'] for f in valid_fragments]).strip()

            if full_line:
                is_duplicate = False
                for prev_line in last_full_lines:
                    if similarity(full_line, prev_line) > SIMILARITY_THRESHOLD:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    last_full_lines.append(full_line)
                    all_captured_lines.append(full_line)
                    if len(last_full_lines) > 10:
                        last_full_lines.pop(0)

            sampled += 1
            frame_index += 1

        if not all_captured_lines:
            return None, "no_text_low_confidence"

        return "\n".join(all_captured_lines[:120]), "success"
    except Exception as e:
        return None, f"error:{e.__class__.__name__}"
    finally:
        cap.release()