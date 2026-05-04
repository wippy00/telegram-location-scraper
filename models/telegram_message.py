from typing import TYPE_CHECKING, Optional, List
from datetime import datetime, timezone
from enum import Enum
from sqlmodel import SQLModel, Field, Column, Text, UniqueConstraint, Relationship

# Evita le importazioni circolari a runtime
if TYPE_CHECKING:
    from .media_job import MediaProcessingJob
    from .location import Location

class PipelineStatus(str, Enum):
    IMPORTED = "imported"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    DISCARDED = "discarded"

class PlatformType(str, Enum):
    INSTAGRAM = "instagram"
    GOOGLE_MAPS = "google_maps"
    TEXT = "text"
    TIKTOK = "tiktok"
    UNKNOWN = "unknown"

class TelegramMessage(SQLModel, table=True):
    """Raw message exactly as received from Telegram."""
    
    __table_args__ = (
        UniqueConstraint("chat_id", "telegram_id", name="uq_chat_message"),
    )
    
    id: Optional[int] = Field(default=None, primary_key=True)
    telegram_id: int = Field(index=True)
    chat_id: int = Field(index=True)
    sender_id: int = Field(index=True)
    sender_name: str
    
    timestamp: datetime = Field(index=True)
    raw_text: str = Field(sa_column=Column(Text))
    
    status: PipelineStatus = Field(default=PipelineStatus.IMPORTED, index=True)
    platform_detected: PlatformType = Field(default=PlatformType.UNKNOWN, index=True)
    
    imported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: Optional[datetime] = Field(default=None)

    # RELAZIONI: Usiamo le stringhe per evitare circular imports
    media_job: Optional["MediaProcessingJob"] = Relationship(
        back_populates="message", 
        cascade_delete=True
    )
    locations: List["Location"] = Relationship(back_populates="message")

    @classmethod
    def from_telethon(cls, message) -> "TelegramMessage":
        """Converte un messaggio Telethon nel modello DB."""
        sender_name = "Unknown"
        sender = getattr(message, "sender", None)
        
        if sender:
            # Funziona sia per utenti (first_name) che per canali (title)
            if hasattr(sender, 'first_name'):
                first = getattr(sender, "first_name") or ""
                last = getattr(sender, "last_name") or ""
                sender_name = f"{first} {last}".strip()
            elif hasattr(sender, 'title'):
                sender_name = getattr(sender, "title")

        # Fallback se sender_name è ancora vuoto
        if not sender_name:
            sender_name = "Unknown User"

        return cls(
            telegram_id=message.id,
            chat_id=message.chat_id or 0,
            sender_id=message.sender_id or 0,
            sender_name=sender_name,
            timestamp=message.date,
            raw_text=message.message or "",
            status=PipelineStatus.IMPORTED,
            platform_detected=PlatformType.UNKNOWN
        )
