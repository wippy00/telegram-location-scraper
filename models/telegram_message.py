from datetime import datetime
from typing import Optional, Any, Dict
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON


class TelegramMessage(SQLModel, table=True):
    """
    Rappresenta un messaggio importato da Telegram.
    
    Campi principali:
    - telegram_id: identificativo univoco del messaggio in Telegram
    - chat_id: ID univoco della chat/gruppo di provenienza
    - sender_id: ID dell'autore del messaggio
    - sender_name: nome visualizzato dell'autore
    - timestamp: data/ora del messaggio
    - raw_text: testo integrale come ricevuto da Telegram (nunca modificato)
    - extracted_data: JSON opzionale con dati strutturati estratti dal parsing
    - status: "imported" | "categorized" | "processed" | "done" | "discarded" per tracciare lo stato di elaborazione
    """
    
    id: Optional[int] = Field(default=None, primary_key=True)
    telegram_id: int = Field(index=True, unique=True)  # Identificativo univoco del messaggio
    chat_id: int = Field(index=True)  # Chat/gruppo di provenienza
    sender_id: int = Field(index=True)  # ID autore
    sender_name: str  # Nome display dell'autore
    timestamp: datetime = Field(index=True)  # Data/ora del messaggio
    raw_text: str  # Testo originale integrale
    extracted_data: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Dati strutturati estratti dal parsing, se applicabile"
    )
    # Status workflow: imported -> categorized -> processed -> done
    status: str = Field(default="imported", index=True)
    # "imported": messaggio appena scaricato da Telegram
    # "categorized": messaggio categorizzato in base al contenuto
    # "processed": in pipeline ma non ancora concluso
    # "done": pipeline conclusa e location aggiunta
    # "discarded": messaggio non valido o non elaborabile
    
    # Categoria assegnata dal MessageCategorizer
    category: Optional[str] = Field(default=None, index=True)
    # "instagram", "maps", "address", "random", o None se non categorizzato
    
    processed_at: Optional[datetime] = Field(default=None)  # Quando è stato elaborato
    imported_at: datetime = Field(default_factory=datetime.utcnow)  # Quando è stato salvato

    @classmethod
    def from_telethon_message(cls, message: Any) -> "TelegramMessage":
        """Build a TelegramMessage instance from a Telethon message object."""
        sender_name = "Unknown"
        sender = getattr(message, "sender", None)
        if sender:
            first_name = getattr(sender, "first_name", "") or ""
            last_name = getattr(sender, "last_name", "") or ""
            full_name = f"{first_name} {last_name}".strip()
            if full_name:
                sender_name = full_name

        return cls(
            telegram_id=getattr(message, "id", 0) or 0,
            chat_id=getattr(message, "chat_id", 0) or 0,
            sender_id=getattr(message, "sender_id", 0) or 0,
            sender_name=sender_name,
            timestamp=getattr(message, "date", None) or datetime.utcnow(),
            raw_text=(getattr(message, "text", None) or getattr(message, "message", "") or ""),
            extracted_data=None,
            status="imported",
        )

    def __repr__(self):
        return (
            f"TelegramMessage(\n"
            f"  telegram_id={self.telegram_id},\n"
            f"  chat_id={self.chat_id},\n"
            f"  sender={self.sender_name},\n"
            f"  timestamp={self.timestamp},\n"
            f"  text={self.raw_text[:50]}...\n"
            f")"
        )
