from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import asyncio
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from pathlib import Path
from datetime import datetime
import logging
from dotenv import load_dotenv

from database.engine import get_engine, init_db
from database.crud import DatabaseCRUD
from models import Location, TelegramMessage, MediaProcessingJob, MarkerCategory
from pipeline.geocoder import GoogleMapsGeocoder

load_dotenv()

# ----------------------------------------
# Pydantic Models for API responses
# ----------------------------------------
class LocationMapMarker(BaseModel):
    """Lightweight location model for map display"""
    id: str
    name: str
    lat: float
    lng: float
    message_id: Optional[int] = None
    category: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    google_maps_url: Optional[str] = None
    google_place_id: Optional[str] = None
    photo_paths: Optional[list[str]] = None
    is_draft: bool = False
    is_deleted: bool = False

    @field_validator('photo_paths', mode='before')
    @classmethod
    def normalize_photo_paths(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Normalize photo paths by converting backslashes to forward slashes."""
        if not v:
            return v
        return [path.replace("\\", "/") for path in v]

    class Config:
        from_attributes = True

class LocationDetail(BaseModel):
    """Full location details"""
    id: str
    name: str
    lat: float
    lng: float
    message_id: Optional[int] = None
    category: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    website: Optional[str] = None
    google_maps_url: Optional[str] = None
    google_place_id: Optional[str] = None
    google_maps_tags: Optional[list[str]] = None
    photo_paths: Optional[list[str]] = None
    is_draft: bool = False
    is_deleted: bool = False
    created_at: datetime

    @field_validator('photo_paths', mode='before')
    @classmethod
    def normalize_photo_paths(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Normalize photo paths by converting backslashes to forward slashes."""
        if not v:
            return v
        return [path.replace("\\", "/") for path in v]

    class Config:
        from_attributes = True

class LocationUpdate(BaseModel):
    """Editable location fields"""
    message_id: Optional[int] = None
    name: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    category: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    website: Optional[str] = None
    google_maps_url: Optional[str] = None
    google_place_id: Optional[str] = None
    google_maps_tags: Optional[list[str]] = None
    photo_paths: Optional[list[str]] = None
    is_draft: Optional[bool] = None
    is_deleted: Optional[bool] = None

    class Config:
        from_attributes = True

class LocationCreate(BaseModel):
    """Payload for creating a new location."""
    message_id: Optional[int] = None
    google_maps_url: str
    is_draft: Optional[bool] = None
    is_deleted: Optional[bool] = None


class LocationPreview(BaseModel):
    """Resolved location data before saving."""
    message_id: Optional[int] = None
    name: str
    lat: float
    lng: float
    category: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    website: Optional[str] = None
    google_maps_url: Optional[str] = None
    google_place_id: Optional[str] = None
    google_maps_tags: Optional[list[str]] = None
    photo_paths: Optional[list[str]] = None

    @field_validator('photo_paths', mode='before')
    @classmethod
    def normalize_photo_paths(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if not v:
            return v
        return [path.replace("\\", "/") for path in v]

class TelegramMessageData(BaseModel):
    id: Optional[int] = None
    telegram_id: Optional[int] = None
    chat_id: Optional[int] = None
    sender_id: Optional[int] = None
    sender_name: str
    timestamp: datetime
    raw_text: str
    status: str
    platform_detected: str
    imported_at: datetime
    processed_at: Optional[datetime] = None

class MediaProcessingJobData(BaseModel):
    """Media processing job information"""
    id: Optional[int] = None
    message_id: int
    source_url: Optional[str] = None
    media_path: Optional[str] = None
    download_status: str
    ocr_status: str
    ai_status: str
    description: Optional[str] = None
    ocr_text: Optional[str] = None
    audio_transcript: Optional[str] = None
    ai_places_json: Optional[list] = None
    result_url: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    logs: Optional[dict] = None
    updated_at: datetime

    class Config:
        from_attributes = True

class LocationSourceResponse(BaseModel):
    telegram_message: Optional[TelegramMessageData] = None
    media_job: Optional[MediaProcessingJobData] = None

class ReviewDraftItem(BaseModel):
    location: LocationDetail
    telegram_message: Optional[TelegramMessageData] = None
    media_job: Optional[MediaProcessingJobData] = None

class ReviewMessageItem(BaseModel):
    telegram_message: TelegramMessageData
    locations: List[LocationDetail]
    media_job: Optional[MediaProcessingJobData] = None

def ensure_google_maps_payload_ok(payload: dict, *, context: str) -> None:
    status = payload.get("status")
    if status == "OK":
        return

    message = payload.get("error_message") or f"Google Maps API returned status '{status}'"
    raise HTTPException(status_code=400, detail=f"{context}: {message}")


import hashlib

ANON_NAMES = [
    "Mario", "Luigi", "Giovanni", "Paolo", "Andrea", "Roberto", "Stefano", 
    "Alessandro", "Giuseppe", "Antonio", "Laura", "Giulia", "Martina", 
    "Chiara", "Sara", "Francesca", "Elena", "Silvia", "Anna", "Maria",
    "Luca", "Matteo", "Francesco", "Davide", "Riccardo", "Federico", 
    "Lorenzo", "Simone", "Marco", "Giacomo", "Alessia", "Elisa", 
    "Valentina", "Marta", "Alice", "Giorgia", "Ilaria", "Eleonora", "Serena", "Beatrice"
]

def anonymize_user(real_name: str) -> str:
    # if not real_name:
    #     return "Anonimo"
    # # L'hash MD5 garantisce che la stessa stringa origini sempre lo stesso identico indice, anche tra riavvii del server
    # hash_val = int(hashlib.md5(real_name.encode('utf-8')).hexdigest(), 16)
    # return ANON_NAMES[hash_val % len(ANON_NAMES)]

    return real_name

def telegram_message_to_data(message: TelegramMessage) -> TelegramMessageData:
    return TelegramMessageData(
        id=message.id,
        telegram_id=None,
        chat_id=None,
        sender_id=None,
        sender_name=anonymize_user(message.sender_name),
        timestamp=message.timestamp,
        raw_text=message.raw_text,
        status=message.status.value,
        platform_detected=message.platform_detected.value,
        imported_at=message.imported_at,
        processed_at=message.processed_at,
    )

def media_job_to_data(job: MediaProcessingJob) -> MediaProcessingJobData:
    return MediaProcessingJobData(
        id=job.id,
        message_id=job.message_id,
        source_url=job.source_url,
        media_path=job.media_path,
        download_status=job.download_status,
        ocr_status=job.ocr_status,
        ai_status=job.ai_status,
        description=job.description,
        ocr_text=job.ocr_text,
        audio_transcript=job.audio_transcript,
        ai_places_json=job.ai_places_json,
        result_url=job.media_path,
        started_at=None,
        finished_at=None,
        logs=job.raw_metadata,
        updated_at=job.updated_at,
    )


# ----------------------------------------
# GeoJSON Models
# ----------------------------------------
class GeoJSONPoint(BaseModel):
    """GeoJSON Point geometry"""
    type: str = "Point"
    coordinates: List[float]  # [longitude, latitude]


class GeoJSONProperties(BaseModel):
    """Properties of a GeoJSON Feature"""
    id: str
    name: str
    category: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    google_maps_url: Optional[str] = None
    google_place_id: Optional[str] = None
    is_draft: bool = False
    is_deleted: bool = False


class GeoJSONFeature(BaseModel):
    """GeoJSON Feature"""
    type: str = "Feature"
    geometry: GeoJSONPoint
    properties: GeoJSONProperties


class GeoJSONFeatureCollection(BaseModel):
    """GeoJSON FeatureCollection"""
    type: str = "FeatureCollection"
    features: List[GeoJSONFeature]


# ----------------------------------------
# FastAPI Setup
# ----------------------------------------
openapi_tags = [
    {
        "name": "System",
        "description": "Health check and general service endpoints.",
    },
    {
        "name": "Media",
        "description": "Media file access endpoints.",
    },
    {
        "name": "Locations",
        "description": "Location retrieval, updates, and lifecycle actions.",
    },
    {
        "name": "Review",
        "description": "Review flows for draft locations and message-grouped review data.",
    },
    {
        "name": "Google Maps",
        "description": "Google Maps URL resolution utilities.",
    },
    {
        "name": "Metadata",
        "description": "Reference and statistics endpoints.",
    },
    {
        "name": "GeoJSON",
        "description": "GeoJSON export endpoints for mapping tools.",
    },
]

app = FastAPI(
    title="Travel Place Visualizer API",
    description="API per visualizzare location su mappa Vue",
    version="1.0.0",
    openapi_tags=openapi_tags,
)

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Enable CORS for Vue frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Modificare con dominio specifico in produzione
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database setup
engine = get_engine("sqlite:////database/database.db")
init_db(engine)
db = DatabaseCRUD(engine)
maps_geocoder = GoogleMapsGeocoder()

# Media directory setup
MEDIA_DIR = Path("/media")

# Mount static media files
if MEDIA_DIR.exists():
    app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")

from fastapi.responses import FileResponse

@app.get("/api/image/{image_path:path}", tags=["Media"])
async def get_image(image_path: str):
    """Retrieve an image by its path/name from the media directory"""
    if not MEDIA_DIR.exists():
        raise HTTPException(status_code=404, detail="Media directory not found")
        
    # Clean up the path
    clean_path = image_path.replace("\\", "/").strip("/")
    if clean_path.startswith("media/"):
        clean_path = clean_path[6:]
        
    file_path = (MEDIA_DIR / clean_path).resolve()
    
    # Ensure it doesn't escape MEDIA_DIR
    try:
        if not file_path.is_relative_to(MEDIA_DIR.resolve()):
            raise HTTPException(status_code=403, detail="Access denied")
    except AttributeError:
        # Fallback for older Python versions
        if not str(file_path).startswith(str(MEDIA_DIR.resolve())):
            raise HTTPException(status_code=403, detail="Access denied")
            
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
        
    return FileResponse(file_path)

# ----------------------------------------
# Endpoints
# ----------------------------------------


def location_to_marker(location: Location) -> LocationMapMarker:
    return LocationMapMarker(
        id=location.id,
        name=location.name,
        lat=location.lat,
        lng=location.lng,
        message_id=location.message_id,
        category=location.category.value if location.category else None,
        description=location.description,
        address=location.address,
        google_maps_url=location.google_maps_url,
        google_place_id=location.google_place_id,
        photo_paths=location.photo_paths,
        is_draft=location.is_draft,
        is_deleted=location.is_deleted,
    )

def resolve_review_sources(location: Location) -> tuple[Optional[TelegramMessage], Optional[MediaProcessingJob]]:
    """Resolve the Telegram message and media job associated with a location."""
    telegram_message = None
    media_job = None
    
    if location.message_id is None:
        return None, None
    
    # Use the relationship if available
    if location.message:
        telegram_message = location.message
        # Get the media job from the message
        if hasattr(telegram_message, 'media_job'):
            media_job = telegram_message.media_job
    
    return telegram_message, media_job


@app.get("/api/health", tags=["System"])
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}


@app.get("/api/locations", response_model=List[LocationMapMarker], tags=["Locations"])
async def get_all_locations(
    category: Optional[str] = Query(None, description="Filter by category"),
    skip_draft: bool = Query(True, description="Exclude draft locations"),
    skip_deleted: bool = Query(True, description="Exclude soft-deleted locations")
):
    """
    Get all locations for map visualization.
    
    Query parameters:
    - category: Filter by MarkerCategory (food, landmark, fun, culture, transport, city, other)
    - skip_draft: Exclude draft/unconfirmed locations (default: True)
    - skip_deleted: Exclude soft-deleted locations (default: True)
    """
    try:
        locations = db.get_all_locations()
        
        markers = []
        for location in locations.values():
            if skip_deleted and location.is_deleted:
                continue

            # Skip draft if requested
            if skip_draft and location.is_draft:
                continue
            
            # Filter by category if specified
            if category and location.category and location.category.value != category:
                continue
            
            markers.append(location_to_marker(location))
        
        return markers
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving locations: {str(e)}")


@app.get("/api/locations/{location_id}/source", response_model=LocationSourceResponse, tags=["Locations"])
async def get_location_source(location_id: str):
    """
    Get the source information (Telegram message and/or media job) for a specific location.
    """
    try:
        with Session(db.engine) as session:
            statement = select(Location).where(Location.id == location_id).options(joinedload(Location.message))  # type: ignore[arg-type]
            location = session.exec(statement).first()
            
            if not location:
                raise HTTPException(status_code=404, detail=f"Location {location_id} not found")
            
            telegram_message, media_job = resolve_review_sources(location)
            
            return LocationSourceResponse(
                telegram_message=telegram_message_to_data(telegram_message) if telegram_message else None,
                media_job=media_job_to_data(media_job) if media_job else None,
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving location source: {str(e)}")


@app.get("/api/locations/{location_id}", response_model=LocationDetail, tags=["Locations"])
async def get_location_detail(location_id: str):
    """
    Get detailed information about a specific location.
    
    Args:
        location_id: The ID of the location
    """
    try:
        location = db.get_location(location_id)
        
        if not location:
            raise HTTPException(status_code=404, detail=f"Location {location_id} not found")
        
        return LocationDetail.from_orm(location)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving location: {str(e)}")


@app.put("/api/locations/{location_id}", response_model=LocationDetail, tags=["Locations"])
async def update_location(location_id: str, payload: LocationUpdate):
    """Update a single location."""
    try:
        location = db.get_location(location_id)

        if not location:
            raise HTTPException(status_code=404, detail=f"Location {location_id} not found")

        if payload.name is not None:
            location.name = payload.name.strip()

        if payload.message_id is not None:
            location.message_id = payload.message_id

        if payload.lat is not None:
            location.lat = payload.lat

        if payload.lng is not None:
            location.lng = payload.lng

        if payload.category is not None:
            location.category = MarkerCategory(payload.category) if payload.category else None

        if payload.description is not None:
            location.description = payload.description.strip() or None

        if payload.address is not None:
            location.address = payload.address.strip() or None

        if payload.website is not None:
            location.website = payload.website.strip() or None

        if payload.google_maps_url is not None:
            location.google_maps_url = payload.google_maps_url.strip() or None

        if payload.google_place_id is not None:
            location.google_place_id = payload.google_place_id.strip() or None

        if payload.google_maps_tags is not None:
            location.google_maps_tags = payload.google_maps_tags

        if payload.photo_paths is not None:
            location.photo_paths = payload.photo_paths

        if payload.is_draft is not None:
            location.is_draft = payload.is_draft

        if payload.is_deleted is not None:
            location.is_deleted = payload.is_deleted

        updated_location = db.update_location(location)
        return LocationDetail.model_validate(updated_location)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating location: {str(e)}")


@app.post("/api/locations", response_model=LocationDetail, tags=["Locations"])
async def create_location(payload: LocationCreate):
    """Create a new location."""
    try:
        google_maps_url = payload.google_maps_url.strip()
        if not google_maps_url:
            raise HTTPException(status_code=400, detail="Google Maps URL is required")

        resolved = await asyncio.to_thread(maps_geocoder.resolve, google_maps_url, 5)
        if not resolved:
            raise HTTPException(status_code=400, detail="Unable to resolve location from the provided Google Maps URL")
        name = str(resolved.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Unable to resolve a name from the provided Google Maps URL")

        lat = resolved.get("lat")
        lng = resolved.get("lng")
        if lat is None or lng is None:
            raise HTTPException(status_code=400, detail="Unable to resolve coordinates from the provided Google Maps URL")

        resolved_category = resolved.get("category")
        if resolved_category is not None:
            resolved_category = getattr(resolved_category, "value", resolved_category)

        location = Location(
            name=name,
            lat=float(lat),
            lng=float(lng),
            message_id=payload.message_id,
            category=MarkerCategory(resolved_category) if resolved_category else None,
            description=str(resolved.get("description") or "").strip() or None,
            address=str(resolved.get("address") or "").strip() or None,
            website=str(resolved.get("website") or "").strip() or None,
            google_maps_url=str(resolved.get("google_maps_url") or google_maps_url).strip(),
            google_place_id=str(resolved.get("google_place_id") or "").strip() or None,
            google_maps_tags=resolved.get("google_maps_tags") or None,
            photo_paths=resolved.get("local_photos") or None,
            is_draft=True if payload.is_draft is None else payload.is_draft,
            is_deleted=False if payload.is_deleted is None else payload.is_deleted,
        )

        created_location = db.insert_location(location)
        return LocationDetail.model_validate(created_location)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating location: {str(e)}")


@app.post("/api/locations/preview", response_model=LocationPreview, tags=["Locations"])
async def preview_location(payload: LocationCreate):
    """Preview the resolved location data without saving it."""
    try:
        google_maps_url = payload.google_maps_url.strip()
        if not google_maps_url:
            raise HTTPException(status_code=400, detail="Google Maps URL is required")

        resolved = await asyncio.to_thread(maps_geocoder.resolve, google_maps_url, 5)
        if not resolved:
            raise HTTPException(status_code=400, detail="Unable to resolve location from the provided Google Maps URL")
        resolved_category = resolved.get("category")
        if resolved_category is not None:
            resolved_category = getattr(resolved_category, "value", resolved_category)

        lat = resolved.get("lat")
        lng = resolved.get("lng")
        if lat is None or lng is None:
            raise HTTPException(status_code=400, detail="Unable to resolve coordinates from the provided Google Maps URL")

        name = str(resolved.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Unable to resolve a name from the provided Google Maps URL")

        return LocationPreview(
            message_id=payload.message_id,
            name=name,
            lat=float(lat),
            lng=float(lng),
            category=str(resolved_category) if resolved_category else None,
            description=str(resolved.get("description") or "").strip() or None,
            address=str(resolved.get("address") or "").strip() or None,
            website=str(resolved.get("website") or "").strip() or None,
            google_maps_url=str(resolved.get("google_maps_url") or google_maps_url).strip(),
            google_place_id=str(resolved.get("google_place_id") or "").strip() or None,
            google_maps_tags=resolved.get("google_maps_tags") or None,
            photo_paths=resolved.get("local_photos") or None,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error previewing location: {str(e)}")


@app.get("/api/locations/by-category/{category}", response_model=List[LocationMapMarker], tags=["Locations"])
async def get_locations_by_category(
    category: str,
    skip_draft: bool = Query(True, description="Exclude draft locations"),
    skip_deleted: bool = Query(True, description="Exclude soft-deleted locations")
):
    """
    Get all locations filtered by category.
    
    Valid categories: food, landmark, fun, culture, transport, city, other
    """
    # Validate category
    valid_categories = [c.value for c in MarkerCategory]
    if category not in valid_categories:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Must be one of: {', '.join(valid_categories)}"
        )
    
    try:
        locations = db.get_all_locations()
        
        markers = []
        for location in locations.values():
            if skip_deleted and location.is_deleted:
                continue

            if skip_draft and location.is_draft:
                continue
            
            if location.category and location.category.value == category:
                markers.append(location_to_marker(location))
        
        return markers
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving locations: {str(e)}")


from sqlmodel import Session, select, col
from sqlalchemy.orm import joinedload
@app.get("/api/review/drafts", response_model=List[ReviewDraftItem], tags=["Review"])
async def get_review_drafts():
    try:
        drafts = []

        with Session(db.engine) as session:
            statement = select(Location).where(
                Location.is_deleted == False, 
                Location.is_draft == True
            ).options(
                joinedload(Location.message)  # type: ignore[arg-type]
            )
            locations = session.exec(statement).unique().all()

            for location in locations:
                telegram_message, media_job = resolve_review_sources(location)

                drafts.append(
                    ReviewDraftItem(
                        location=LocationDetail.model_validate(location),
                        telegram_message=telegram_message_to_data(telegram_message) if telegram_message else None,
                        media_job=media_job_to_data(media_job) if media_job else None,
                    )
                )

        return drafts
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving review drafts: {str(e)}")


@app.get("/api/review/messages", response_model=List[ReviewMessageItem], tags=["Review"])
async def get_review_messages(
    only_drafts: bool = Query(True, description="Include only non-deleted draft locations"),
    include_without_locations: bool = Query(False, description="Include messages that have no locations after filters"),
    limit: Optional[int] = Query(None, ge=1, description="Max number of messages returned after filtering")
):
    """Return review payload grouped by Telegram message with nested locations and optional media job."""
    try:
        items: List[ReviewMessageItem] = []

        with Session(db.engine) as session:
            statement = (
                select(TelegramMessage)
                .order_by(col(TelegramMessage.timestamp).desc())
                .options(
                    joinedload(TelegramMessage.locations),  # type: ignore[arg-type]
                    joinedload(TelegramMessage.media_job)  # type: ignore[arg-type]
                )
            )
            messages = session.exec(statement).unique().all()

            for message in messages:
                message_locations = list(message.locations or [])

                if only_drafts:
                    message_locations = [
                        location for location in message_locations
                        if (not location.is_deleted) and location.is_draft
                    ]

                if not include_without_locations and not message_locations:
                    continue

                item = ReviewMessageItem(
                    telegram_message=telegram_message_to_data(message),
                    locations=[LocationDetail.model_validate(location) for location in message_locations],
                    media_job=media_job_to_data(message.media_job) if message.media_job else None,
                )
                items.append(item)

                if limit is not None and len(items) >= limit:
                    break

        return items
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving review messages: {str(e)}")


@app.post("/api/locations/{location_id}/soft-delete", response_model=LocationDetail, tags=["Locations"])
async def soft_delete_location(location_id: str):
    try:
        location = db.get_location(location_id)
        if not location:
            raise HTTPException(status_code=404, detail=f"Location {location_id} not found")

        if not location.is_deleted:
            location.is_deleted = True

        updated_location = db.update_location(location)
        return LocationDetail.model_validate(updated_location)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error soft deleting location: {str(e)}")


@app.post("/api/locations/{location_id}/restore", response_model=LocationDetail, tags=["Locations"])
async def restore_location(location_id: str):
    try:
        location = db.get_location(location_id)
        if not location:
            raise HTTPException(status_code=404, detail=f"Location {location_id} not found")

        if location.is_deleted:
            location.is_deleted = False

        updated_location = db.update_location(location)
        return LocationDetail.model_validate(updated_location)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error restoring location: {str(e)}")


@app.get("/api/categories", tags=["Metadata"])
async def get_categories():
    """Get list of available marker categories"""
    return {
        "categories": [c.value for c in MarkerCategory]
    }


@app.get("/api/stats", tags=["Metadata"])
async def get_statistics():
    """Get statistics about locations"""
    try:
        locations = db.get_all_locations()
        
        stats = {
            "total_locations": len(locations),
            "deleted_locations": sum(1 for l in locations.values() if l.is_deleted),
            "active_locations": sum(1 for l in locations.values() if not l.is_deleted),
            "confirmed_locations": sum(1 for l in locations.values() if not l.is_deleted and not l.is_draft),
            "draft_locations": sum(1 for l in locations.values() if not l.is_deleted and l.is_draft),
            "by_category": {},
        }
        
        for location in locations.values():
            if location.is_deleted:
                continue

            # Count by category
            if location.category:
                cat = location.category.value
                stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1
        
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving statistics: {str(e)}")


# ----------------------------------------
# GeoJSON Endpoints
# ----------------------------------------

def location_to_geojson_feature(location: Location) -> GeoJSONFeature:
    """Convert a Location object to GeoJSON Feature"""
    return GeoJSONFeature(
        geometry=GeoJSONPoint(coordinates=[location.lng, location.lat]),
        properties=GeoJSONProperties(
            id=location.id,
            name=location.name,
            category=location.category.value if location.category else None,
            description=location.description,
            address=location.address,
            google_maps_url=location.google_maps_url,
            google_place_id=location.google_place_id,
            is_draft=location.is_draft,
            is_deleted=location.is_deleted
        )
    )
    


@app.get("/api/geojson", response_model=GeoJSONFeatureCollection, tags=["GeoJSON"])
async def get_geojson(
    category: Optional[str] = Query(None, description="Filter by category"),
    skip_draft: bool = Query(True, description="Exclude draft locations"),
    skip_deleted: bool = Query(True, description="Exclude soft-deleted locations")
):
    """
    Get all locations as GeoJSON FeatureCollection.
    
    Perfect for use with mapping libraries like Leaflet or Mapbox.
    
    Query parameters:
    - category: Filter by MarkerCategory
    - skip_draft: Exclude draft/unconfirmed locations (default: True)
    """
    try:
        locations = db.get_all_locations()
        features = []
        
        for location in locations.values():
            if skip_deleted and location.is_deleted:
                continue

            # Skip draft if requested
            if skip_draft and location.is_draft:
                continue
            
            # Filter by category if specified
            if category and location.category and location.category.value != category:
                continue
            
            feature = location_to_geojson_feature(location)
            features.append(feature)
        
        return GeoJSONFeatureCollection(features=features)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving GeoJSON: {str(e)}")


@app.get("/api/geojson/{category}", response_model=GeoJSONFeatureCollection, tags=["GeoJSON"])
async def get_geojson_by_category(
    category: str,
    skip_draft: bool = Query(True, description="Exclude draft locations"),
    skip_deleted: bool = Query(True, description="Exclude soft-deleted locations")
):
    """
    Get locations filtered by category as GeoJSON.
    
    Valid categories: food, landmark, fun, culture, transport, city, other
    """
    # Validate category
    valid_categories = [c.value for c in MarkerCategory]
    if category not in valid_categories:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Must be one of: {', '.join(valid_categories)}"
        )
    
    try:
        locations = db.get_all_locations()
        features = []
        
        for location in locations.values():
            if skip_deleted and location.is_deleted:
                continue

            if skip_draft and location.is_draft:
                continue
            
            if location.category and location.category.value == category:
                feature = location_to_geojson_feature(location)
                features.append(feature)
        
        return GeoJSONFeatureCollection(features=features)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving GeoJSON: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
