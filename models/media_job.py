from typing import TYPE_CHECKING, Optional, Dict, Any, List
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field, Column, Text, JSON, Relationship

if TYPE_CHECKING:
    from .telegram_message import TelegramMessage

class MediaProcessingJob(SQLModel, table=True):
    """
    Traccia lo stato di elaborazione dei media (Video, Immagini)
    e delle operazioni AI/OCR associati a un messaggio.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Foreign Key verso TelegramMessage
    message_id: int = Field(foreign_key="telegrammessage.id", index=True, unique=True)
    message: "TelegramMessage" = Relationship(back_populates="media_job")

    source_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    media_path: Optional[str] = Field(default=None, sa_column=Column(Text)) 
    
    # Tracking degli step
    download_status: str = Field(default="pending", index=True)
    ocr_status: str = Field(default="pending", index=True)
    ai_status: str = Field(default="pending", index=True)

    # Dati estratti grezzi
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    ocr_text: Optional[str] = Field(default=None, sa_column=Column(Text))
    audio_transcript: Optional[str] = Field(default=None, sa_column=Column(Text))
    ai_places_json: Optional[List[Dict[str, Any]]] = Field(default=None, sa_column=Column(JSON))
    raw_metadata: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))

    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))