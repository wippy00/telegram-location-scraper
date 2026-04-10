from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON, Text


class InstagramReel(SQLModel, table=True):
    """Raw extraction snapshot for an Instagram reel/post link."""

    id: Optional[int] = Field(default=None, primary_key=True)
    telegram_id: int = Field(index=True, unique=True)
    source_url: str = Field(sa_column=Column(Text))

    shortcode: Optional[str] = Field(default=None, index=True)
    extraction_method: Optional[str] = Field(default=None, index=True)

    name: Optional[str] = None
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    uploader: Optional[str] = None

    video_path: Optional[str] = Field(default=None, sa_column=Column(Text))
    video_download_status: Optional[str] = Field(default=None, index=True)

    ocr_text: Optional[str] = Field(default=None, sa_column=Column(Text))
    ocr_status: Optional[str] = Field(default=None, index=True)

    audio_transcript: Optional[str] = Field(default=None, sa_column=Column(Text))
    asr_status: Optional[str] = Field(default=None, index=True)

    ai_source: Optional[str] = Field(default=None, index=True)
    ai_status: Optional[str] = Field(default=None, index=True)
    ai_places_json: Optional[List[Dict[str, Any]]] = Field(default=None, sa_column=Column(JSON))

    pipeline_status: str = Field(default="pending_download", index=True)

    raw_payload: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))

    extracted_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)
