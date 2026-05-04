import os
import sys
from pathlib import Path

# Aggiungi la directory radice del progetto al Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from telethon.sync import TelegramClient as TgClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

# Nuovi import del database separato
from database.engine import get_engine, init_db
from database.crud import DatabaseCRUD
from models import TelegramMessage

load_dotenv()

# --- CONFIGURAZIONE ---
api_id = int(os.getenv("TELEGRAM_API_ID", "0"))
api_hash = os.getenv("TELEGRAM_API_HASH", "")
phone_number = os.getenv("TELEGRAM_PHONE", "")
chat_id = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
topic_root_id = int(os.getenv("TELEGRAM_TOPIC_ROOT_ID", "65"))
topic_limit = int(os.getenv("TELEGRAM_TOPIC_LIMIT", "1000"))
database_path = os.getenv("DATABASE_PATH", "sqlite:///data/database.db")
session_name = "telegram_session"

if api_id == 0 or not api_hash:
    raise RuntimeError("Config Telegram mancante: TELEGRAM_API_ID / TELEGRAM_API_HASH")

# --- INIZIALIZZAZIONE DATABASE ---
engine = get_engine(database_path)
init_db(engine) # Assicura che le tabelle esistano
db = DatabaseCRUD(engine)

# --- AVVIO TELETHON ---
with TgClient(session_name, api_id, api_hash) as client:
    client: TgClient
    client.connect()

    # Gestione Autenticazione (Userbot)
    if not client.is_user_authorized():
        client.send_code_request(phone_number)
        code = input("Enter the code: ").strip()

        try:
            client.sign_in(phone=phone_number, code=code)
        except SessionPasswordNeededError:
            password = input("2FA enabled. Enter Telegram password: ").strip()
            client.sign_in(password=password)
        except PhoneCodeInvalidError:
            raise RuntimeError("Codice Telegram non valido.")

    print(f"Scaricando i messaggi dal topic {topic_root_id} della chat {chat_id}...")

    # Recupero Messaggi
    messages = client.iter_messages(
        chat_id,
        limit=topic_limit,
        reply_to=topic_root_id,
        reverse=True, # Ordine cronologico dal più vecchio al più recente
    )

    saved_count = 0
    ignored_count = 0

    for message in messages:
        # Se il messaggio non ha testo (es. è un evento di sistema), saltalo
        if not message.message:
            continue

        # Convertiamo l'oggetto di Telethon nel nostro modello SQLModel
        telegram_message = TelegramMessage.from_telethon(message)
        
        # Filtro Custom: Ignora messaggi marcati con #ignore
        if "#ignore" in telegram_message.raw_text.lower():
            ignored_count += 1
            continue
            
        try:
            # USIAMO UPSERT: Niente più errori di "Already Exists"
            db.upsert_telegram_message(telegram_message)
            saved_count += 1
            
            # (Opzionale) stampa solo i primi 50 caratteri per non intasare il terminale
            snippet = telegram_message.raw_text[:50].replace("\n", " ")
            print(f"[OK] Salvato: {snippet}...")
            
        except Exception as e:
            print(f"[ERRORE] Impossibile salvare il messaggio {telegram_message.telegram_id}: {e}")

    print("-" * 30)
    print(f"Importazione completata: {saved_count} salvati, {ignored_count} ignorati.")