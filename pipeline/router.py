from models import PlatformType
from .categorizer import categorize_message

from .extractors.gmaps_extractor import MapsExtractor
from .extractors.instagram_extractor import InstagramExtractor
from .extractors.address_extractor import AddressExtractor
from database.crud import DatabaseCRUD


async def extract_locations_from_message(text: str, message_id: int = None, db: DatabaseCRUD = None) -> dict: # type: ignore
    
    platform = categorize_message(text)    
    
    result = {}

    if platform == PlatformType.GOOGLE_MAPS:
        result = await MapsExtractor().process(text)
    
    elif platform == PlatformType.INSTAGRAM:
        result = await InstagramExtractor(db=db, message_id=message_id).process(text)
        
    elif platform == PlatformType.TEXT:
        result = await AddressExtractor().process(text)
        
    else:
        result = {"locations": [], "error": None} # Ignora messaggi sconosciuti

    result["platform_detected"] = platform.value if platform else None # type: ignore
    return result