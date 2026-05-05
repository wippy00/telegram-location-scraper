from models.location import MarkerCategory


def infer_location_category(text: str) -> MarkerCategory:
    t = (text or "").lower()

    if any(k in t for k in ["food", "cibo", "ramen", "sushi", "izakaya", "restaurant", "brewery", "market"]):
        return MarkerCategory.FOOD
    if any(k in t for k in ["station", "airport", "metro", "train"]):
        return MarkerCategory.TRANSPORT
    if any(k in t for k in ["temple", "shrine", "museum", "castle"]):
        return MarkerCategory.CULTURE
    if any(k in t for k in ["city", "tokyo", "kyoto", "osaka", "kamakura"]):
        return MarkerCategory.CITY

    return MarkerCategory.OTHER
