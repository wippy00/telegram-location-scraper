import uuid
from typing import TYPE_CHECKING, Optional, List
from datetime import datetime, timezone
from enum import Enum
from sqlmodel import SQLModel, Field, Column, Text, JSON, Relationship
from sqlalchemy.types import Double

if TYPE_CHECKING:
    from .telegram_message import TelegramMessage

class MarkerCategory(str, Enum):
    FOOD = "food"
    LANDMARK = "landmark"
    FUN = "fun"
    CULTURE = "culture"
    TRANSPORT = "transport"
    CITY = "city"
    OTHER = "other"

class Location(SQLModel, table=True):
    """Luogo finale estratto dalla pipeline."""
    
    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    
    # Foreign Key verso TelegramMessage
    message_id: Optional[int] = Field(default=None, foreign_key="telegrammessage.id", index=True)
    message: Optional["TelegramMessage"] = Relationship(back_populates="locations")

    name: str = Field(max_length=255)
    lat: float = Field(sa_column=Column(Double))
    lng: float = Field(sa_column=Column(Double))
    
    category: Optional[MarkerCategory] = None
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Info Mappe e Deduplicazione
    address: Optional[str] = None
    website: Optional[str] = None
    google_maps_tags: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    google_maps_url: Optional[str] = None
    google_place_id: Optional[str] = Field(default=None, index=True)
    
    photo_paths: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    
    # Workflow
    is_draft: bool = Field(default=True, index=True)
    is_deleted: bool = Field(default=False, index=True)
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))