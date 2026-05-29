import os
import sys
from pathlib import Path

# Aggiungi la directory radice del progetto al Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from telethon import events
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
session_file = "/telegram_session/telegram_session"

if api_id == 0 or not api_hash:
    raise RuntimeError("Config Telegram mancante: TELEGRAM_API_ID / TELEGRAM_API_HASH")

# --- INIZIALIZZAZIONE DATABASE ---
engine = get_engine(database_path)
init_db(engine) # Assicura che le tabelle esistano
db = DatabaseCRUD(engine)


def is_message_in_target_topic(message) -> bool:
    """Riconosce i messaggi appartenenti al topic configurato."""
    reply_to = getattr(message, "reply_to", None)
    if not reply_to:
        return False

    reply_top_id = getattr(reply_to, "reply_to_top_id", None)
    reply_msg_id = getattr(reply_to, "reply_to_msg_id", None)

    return reply_top_id == topic_root_id or reply_msg_id == topic_root_id


def save_telegram_message(message) -> bool:
    """Converte e salva un messaggio Telegram se valido."""
    if not message.message:
        return False

    telegram_message = TelegramMessage.from_telethon(message)

    if telegram_message.telegram_id is None:
        return False

    existing_message = db.get_telegram_message(telegram_message.chat_id, telegram_message.telegram_id)
    if existing_message:
        return False

    if "#ignore" in telegram_message.raw_text.lower():
        return False

    db.upsert_telegram_message(telegram_message)
    snippet = telegram_message.raw_text[:50].replace("\n", " ")
    print(f"[OK] Salvato: {snippet}...")
    return True


def import_missing_messages(client: TgClient, last_seen_telegram_id: int) -> int:
    """Recupera eventuali messaggi persi prima dell'avvio del listener."""
    imported_count = 0

    messages = client.iter_messages(
        chat_id,
        min_id=last_seen_telegram_id,
        limit=topic_limit,
        reverse=True,
    )

    for message in messages:
        if not is_message_in_target_topic(message):
            continue

        if message.id <= last_seen_telegram_id:
            continue

        if save_telegram_message(message):
            imported_count += 1
            last_seen_telegram_id = message.id

    return imported_count

# --- AVVIO TELETHON ---
with TgClient(session_file, api_id, api_hash) as client:
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

    latest_message = db.get_latest_telegram_message(chat_id)
    last_seen_telegram_id = latest_message.telegram_id if latest_message else 0

    print(f"Ascolto attivo per il topic {topic_root_id} della chat {chat_id}...")
    if last_seen_telegram_id > 0:
        print(f"Recupero eventuali messaggi mancanti dopo l'ID Telegram {last_seen_telegram_id}.")

    try:
        imported_count = import_missing_messages(client, last_seen_telegram_id)
        if imported_count:
            print(f"Recupero iniziale completato: {imported_count} nuovi messaggi salvati.")

        @client.on(events.NewMessage(chats=chat_id))
        async def on_new_message(event):
            if not is_message_in_target_topic(event.message):
                return

            if save_telegram_message(event.message):
                print(f"[EVENT] Nuovo messaggio ricevuto nel topic {topic_root_id}.")

        print("Listener Telegram avviato. In attesa di nuovi messaggi...")
        client.run_until_disconnected()

    except KeyboardInterrupt:
        print("\nImporter Telegram fermato manualmente.")