import os
from dotenv import load_dotenv
from telethon.sync import TelegramClient as TgClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

from data.database import Database
from models.telegram_message import TelegramMessage

load_dotenv()

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

with TgClient(session_name, api_id, api_hash) as client:
    client: TgClient
    client.connect()

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

    messages = client.iter_messages(
        chat_id,
        limit=topic_limit,
        reply_to=topic_root_id,
        reverse=True,
    )

    db = Database(database_path)

    for message in messages:
        telegram_message = TelegramMessage.from_telethon_message(message)
        
        if "#ignore" in telegram_message.raw_text.lower():
            continue
            
        try:
            db.insert_telegram_message(telegram_message)
        except Exception as e:
            if "already exists." in str(e):
                pass
            else:
                print(f"Errore salvando messaggio Telegram {telegram_message.telegram_id}: {e}")
        print(telegram_message.raw_text)

