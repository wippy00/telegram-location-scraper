import os
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv


# Assicurati di avere queste librerie installate:
# pip install google-genai python-dotenv

# 1. Recupera la chiave dalle variabili d'ambiente (o incollala qui per il test)
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY)

def test_video_analysis(video_path: str, description: str):
    if not os.path.exists(video_path):
        print(f"File non trovato: {video_path}")
        return

    print(f"1. Caricamento del video '{video_path}' su Gemini...")
    # L'API supporta video fino a 2GB!
    video_file = client.files.upload(file=video_path)

    print(f"2. Attesa dell'elaborazione (questo richiede un po' a seconda del video)...")
    while video_file.state == "PROCESSING":
        print(".", end="", flush=True)
        time.sleep(3)
        video_file = client.files.get(name=video_file.name)
    print("\nVideo pronto per l'analisi!")

    if video_file.state == "FAILED":
        print("Errore: Impossibile elaborare il video sui server Google.")
        return

    # Usiamo lo stesso identico prompt testato che avevi nel tuo file llm_extractor.py 
    # ma lo adattiamo lievemente all'input multimodale (Video + Testo)
    system_prompt = (
        "You are an expert travel information extractor.\n"
        "You extract real-world visitable places from informal travel content (video and text description).\n"
        "Return STRICT JSON only. No explanations."
    )

    task_prompt = (
        "Watch the attached video and read the description.\n"
        "Extract real-world places (restaurants, landmarks, cities, etc.) from the content.\n\n"
        "CRITICAL:\n"
        "- Extract ONLY actual physical places that people can visit\n"
        "- Do NOT extract concepts, foods, dishes, or menu items\n"
        "- Do NOT extract brand names unless they clearly refer to a real place\n"
        "- Do NOT return empty results if at least one valid place exists\n\n"
        "STRICT PLACE DEFINITION:\n"
        "A valid place MUST be a physical location that exists on a map/real world. EVEN IF they do not say the EXACT NAME of the place (e.g. '8th century temple' or 'shrine with Mt. Fuji view' MUST be extracted as places!).\n\n"
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
        "- If a point of interest or temple or shop is described but without its specific proper name, extract it using the descriptive name provided (e.g. 'Stunning shrine with Mt Fuji views', 'ocean pier').\n"
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

    combined_input = [
        video_file,
        system_prompt,
        task_prompt,
        f"Description text:\n{description}"
    ]

    print("3. Richiesta a Gemini in corso... Attendi...")
    try:
        response = client.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=combined_input,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        
        print("\n--- RISPOSTA JSON DA GEMINI ---")
        print(response.text)
        
    except Exception as e:
        print(f"Errore durante la generazione: {e}")
    finally:
        print("\n4. Eliminazione del file dal server per liberare il cloud e rispettare la privacy...")
        client.files.delete(name=video_file.name)
        print("Fatto. Pulizia completata.")

if __name__ == "__main__":
    # Inserisci qua sotto il percorso assoluto o relativo di un tuo video .mp4 di test
    TEST_VIDEO_PATH = "media/instagram_videos/DUsrl1lDVw7.mp4"
    TEST_DESCRIPTION = """Tokyo‘s most underrated day trip is…👀

This is the Boso Peninsula in Chiba, the entrypoint into Tokyo Bay. Unlike the other side of Kanagawa with cities such as Yokohama and nearby Kamakura, it is still very off the beaten path but with stunning scenery. 

To get here, the best way is a highway bus from either Tokyo or Shinjuku Station to Tateyama, the biggest city in the region. They run roughly once every hour and you can just get on with your usual Suica or Pasmo IC Card. A once way ride takes around 1.5-2 hours depending on traffic.

My first stop from Tateyama was a quick 30 minute bus ride away: this stunning shrine with the perfect views out on Mt. Fuji. In order to have the best chances to see Mt. Fuji, you want to go on a clear day, ideally in winter, as that’s where the air is the clearest. Besides the Torii gate looking out on Mt. Fuji, the shrine building up on a hill is also worth exploring with even more beautiful Ocean Views.

My next stop was around an hour away by bus, with a quick transfer at the earlier Tateyama Station: This stunning temple from the 8th century built into a rocky cliffside. It reminded me a lot of the Tiger’s next in Bhutan but without any noticeable amount of tourists there. The views from the top of the Temple were once again beautiful, overlooking Tateyama and the ocean below. 

From there, I walked around 30 minutes to my final stop of the day and a bucket list spot of mine for years: the Haraoka Beaches. This stunning place is a rare example of a wooden pier in Japan stretching out into the ocean with views out on Fuji in the distance. If you stay until just after the sunset when the lanterns are turned on, the scenery really looks straight out of Ghibli Film. And with that, I was able to catch the bus back to Shinjuku from nearby Tomiura Club Center.

I seriously hope that you will consider adding the Boso Peninsula to your next Japan trip as this area really deserves to be explored by more people""" 
    test_video_analysis(TEST_VIDEO_PATH, TEST_DESCRIPTION)
