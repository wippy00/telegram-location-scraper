from typing import List, Optional, Type, TypeVar , Any, Generic
from datetime import datetime
from enum import Enum

from sqlmodel import LargeBinary, SQLModel, Field, Relationship
from sqlalchemy.orm import Mapped
from sqlalchemy import Column, JSON, types, Double
from pydantic import computed_field


#----------------------------------------
#   Enums
#----------------------------------------
class MarkerCategory(str, Enum):
    FOOD = "food"
    LANDMARK = "landmark"
    FUN = "fun"
    CULTURE = "culture"
    TRANSPORT = "transport"
    CITY = "city"
    OTHER = "other"



#----------------------------------------
#   Marker Model
#----------------------------------------
class Location(SQLModel, table=True):
    id: str = Field(primary_key=True, max_length=32, min_length=32)
    name: str = Field(max_length=255)
    lat: float = Field(sa_column=Column(Double))
    lng: float = Field(sa_column=Column(Double))

    telegram_message_id: Optional[int] = Field(
        default=None,
        foreign_key="telegrammessage.telegram_id",
        index=True,
    )
  
    description: Optional[str] = None
    google_maps_url: Optional[str] = None
    source_url: Optional[str] = None
    photo_paths: Optional[list[str]] = Field(default=None, sa_column=Column(JSON))
    
    category: Optional[MarkerCategory] = None
    
    # Deduplication and tracking fields
    checksum: Optional[str] = Field(default=None, index=True, unique=True)  # Hash di (name, lat, lng) per deduplication
    is_draft: bool = Field(default=True)  # True se estratto da messaggio (needs_review), False se confermato
    platform: Optional[str] = Field(default=None)  # Fonte: "instagram", "maps", "address", "manual"
    is_deleted: bool = Field(default=False, index=True)
    deleted_at: Optional[datetime] = Field(default=None)

    def __repr__(self):
        return (
            f"\n"
            f"    {'id':<12} {self.id}\n"
            f"    {'name':<12} {self.name}\n"
            # f"    {'description':<12} {self.description},\n"
            # f"    {'lat':<12} {self.lat},\n"
            # f"    {'lng':<12} {self.lng},\n"
            # f"    {'images':<12} {self.images}\n"
            f"    {'file':<12} {self.source_url}\n"
            f"\n"
    )

    def __str__(self):
        return self.__repr__()
    

