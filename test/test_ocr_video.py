import cv2
import numpy as np
import easyocr
import re
from difflib import SequenceMatcher

def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

reader = easyocr.Reader(["en"], gpu=False)

# --- CONFIGURAZIONE FILTRI ---
BLACKLIST = {"power", "password", "top", "menu", "app", "battery", "wifi", "edition", "fuji", "advisor"}
SIMILARITY_THRESHOLD = 0.7 

def clean_text(text):
    text = re.sub(r'^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$', '', text)
    text = re.sub(r'[^a-zA-Z0-9\s]', ' ', text)
    text = " ".join(text.split())
    return text

def is_junk(text, prob):
    t_low = text.lower().strip()
    if any(word in t_low for word in BLACKLIST): return True
    if len(text) < 3: return True # Abbassato a 3 per non perdere parole come "the", "and" se sono parte di una frase
    if not re.search(r'[aeiouAEIOU]', text) and len(text) > 3: return True
    return False

def show_image(frame, window_name="frame", max_height=720):
    h, w = frame.shape[:2]
    if h > max_height:
        scale = max_height / h
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    cv2.imshow(window_name, frame)

video = cv2.VideoCapture("data/instagram_videos/DQWjnmYE6Tv.mp4")
fps = video.get(cv2.CAP_PROP_FPS) or 30
step = int(round(fps)) 

last_full_lines = [] # Memoria per le intere righe
i = 0

while True:
    ok, frame = video.read()
    if not ok: break

    if i % step != 0:
        i += 1
        continue

    # --- PRE-PROCESSING ---
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    denoised = cv2.medianBlur(gray, 3)
    upscaled = cv2.resize(denoised, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    kernel_sharpening = np.array([[-1,-1,-1], [-1, 9,-1], [-1,-1,-1]])
    sharpened = cv2.filter2D(upscaled, -1, kernel_sharpening)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(sharpened)

    results = reader.readtext(enhanced)

    # 1. FILTRAGGI E RACCOLTA
    valid_fragments = []
    for (bbox, text, prob) in results:
        cleaned = clean_text(text)
        if prob >= 0.5 and not is_junk(cleaned, prob):
            # Salviamo il testo insieme alle coordinate per l'ordinamento
            # bbox[0][1] è la coordinata Y (altezza), bbox[0][0] è la X (posizione orizzontale)
            valid_fragments.append({
                'text': cleaned,
                'x': bbox[0][0],
                'y': bbox[0][1]
            })

    # 2. ORDINAMENTO GEOMETRICO
    # Ordiniamo prima per Y (dall'alto in basso) e poi per X (da sinistra a destra)
    # Usiamo una tolleranza per la Y (es. 20 pixel) così se due parole sono sulla stessa riga 
    # ma una è un pixel più in alto, vengono comunque considerate sulla stessa riga.
    valid_fragments.sort(key=lambda b: (b['y'] // 20, b['x']))

    # 3. UNIONE IN UN'UNICA RIGA
    full_line = " ".join([f['text'] for f in valid_fragments])

    # 4. FILTRO RIPETIZIONI SULLA RIGA INTERA
    if full_line.strip():
        is_duplicate = False
        for prev_line in last_full_lines:
            if similarity(full_line, prev_line) > SIMILARITY_THRESHOLD:
                is_duplicate = True
                break
        
        if not is_duplicate:
            print(f"Schermata: {full_line}")
            last_full_lines.append(full_line)
            if len(last_full_lines) > 10:
                last_full_lines.pop(0)

    # Debug Visivo
    for frag in valid_fragments:
        # Ricostruiamo il bbox per il disegno (diviso per 2 x causa upscaling)
        # Nota: qui usiamo i risultati originali per disegnare, per semplicità
        pass 

    show_image(frame, "Risultato Finale")
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break
    i += 1

video.release()
cv2.destroyAllWindows()