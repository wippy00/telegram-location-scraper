import asyncio
import os
from dotenv import load_dotenv

from database.engine import get_engine, init_db
from database.crud import DatabaseCRUD
from models import PipelineStatus, Location

from pipeline.router import extract_locations_from_message

load_dotenv()

async def run_worker():
    """Loop principale che scansiona il DB e processa i messaggi."""
    
    # 1. Configurazione Database
    db_path = "sqlite:////database/database.db"
    engine = get_engine(db_path)
    init_db(engine)
    db = DatabaseCRUD(engine)

    print("Worker Pipeline avviato. In attesa di messaggi...")

    while True:
        try:
            pending_messages = db.get_unprocessed_messages(status=PipelineStatus.IMPORTED)

            if not pending_messages:
                await asyncio.sleep(5)
                continue

            print(f"\nTrovati {len(pending_messages)} messaggi da analizzare.")

            for msg in pending_messages:
                print(f"Elaborazione messaggio ID {msg.id}...")
                db.update_message_status(msg.id, PipelineStatus.PROCESSING) # type: ignore
                
                try:
                    extracted_data = await extract_locations_from_message(msg.raw_text, msg.id, db) # type: ignore
                    
                    # Controlla se c'è un errore
                    if extracted_data.get("error"):
                        error_msg = extracted_data.get("error")
                        print(f"Errore durante l'elaborazione: {error_msg}")
                        db.update_message_status(msg.id, PipelineStatus.FAILED) #type: ignore
                        continue
                    
                    # Salva il platform_detected
                    platform_detected = extracted_data.get("platform_detected")
                    if platform_detected:
                        db.update_message_platform(msg.id, platform_detected) #type: ignore

                    if not extracted_data or not extracted_data.get("locations"):
                        print("Nessun luogo trovato nel messaggio. Scartato.")
                        db.update_message_status(msg.id, PipelineStatus.DISCARDED) #type: ignore
                        continue

                    # Salva i luoghi
                    for loc_data in extracted_data["locations"]:
                        new_location = Location(
                            message_id=msg.id,
                            name=loc_data["name"],
                            lat=loc_data["lat"],
                            lng=loc_data["lng"],
                            description=loc_data.get("description"),
                            address=loc_data.get("address"),
                            website=loc_data.get("website"),
                            category=loc_data.get("category"),
                            google_maps_tags=loc_data.get("categories"),
                            google_maps_url=loc_data.get("google_maps_url"),
                            google_place_id=loc_data.get("google_place_id"),
                            photo_paths=loc_data.get("local_photos", [])
                        )
                        db.insert_location(new_location)
                        print(f"Salvato: {new_location.name} ({new_location.lat}, {new_location.lng})")

                    db.update_message_status(msg.id, PipelineStatus.DONE) #type: ignore
                    
                except Exception as e:
                    print(f"Errore elaborando messaggio {msg.id}: {e}")
                    db.update_message_status(msg.id, PipelineStatus.FAILED) #type: ignore
                    continue

        except Exception as e:
            print(f"Errore critico nel ciclo principale: {e}")
            # Se c'è un errore, aspetta un po' prima di riprovare per non impazzire
            await asyncio.sleep(10)

if __name__ == "__main__":

    try:
        # Avviamo il worker in modalità asincrona
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        print("\nWorker fermato manualmente.")