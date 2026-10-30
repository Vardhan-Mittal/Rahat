"""Official alert feeds: NDMA SACHET (India, CAP) and GDACS (global disaster events)."""

import math
from datetime import datetime, timedelta, timezone

from ..geo import km
from ..http import Timer, get_json, mark

SACHET = "https://sachet.ndma.gov.in/cap_public_website/FetchAllAlertDetails"
GDACS = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"

COLOR_LEVEL = {"green": "green", "yellow": "yellow", "orange": "orange", "red": "red"}


async def sachet() -> list[dict]:
    with Timer() as t:
        try:
            raw = await get_json(SACHET, ttl=300, timeout=15)
        except Exception as e:
            mark("SACHET", "down", str(e))
            raise
    mark("SACHET", "live", f"{len(raw)} active alerts", t.elapsed)
    out = []
    for a in raw:
        try:
            lon, lat = (float(x) for x in str(a.get("centroid", "")).split(","))
        except ValueError:
            continue
        area = float(a.get("area_covered") or 0)
        out.append({
            "id": str(a.get("identifier")),
            "type": a.get("disaster_type"),
            "area": a.get("area_description"),
            "source": a.get("alert_source"),
            "level": COLOR_LEVEL.get(str(a.get("severity_color", "")).lower(), "yellow"),
            "message": a.get("warning_message"),
            "start": a.get("effective_start_time"),
            "end": a.get("effective_end_time"),
            "lat": lat,
            "lon": lon,
            # Equivalent radius of the alert area, so we can tell whether a point is covered.
            "radius_km": math.sqrt(area / math.pi) if area > 0 else 25.0,
        })
    return out


def covering(alerts: list[dict], lat: float, lon: float) -> list[dict]:
    """Alerts whose area (approximated as a circle around the centroid) contains the point."""
    return [a for a in alerts if km(lat, lon, a["lat"], a["lon"]) <= a["radius_km"] * 1.15]


async def gdacs() -> list[dict]:
    with Timer() as t:
        try:
            raw = await get_json(GDACS, params={"country": "IND", "limit": 30}, ttl=900, timeout=15)
        except Exception as e:
            mark("GDACS", "down", str(e))
            raise
    mark("GDACS", "live", "", t.elapsed)
    now = datetime.now(timezone.utc)
    out = []
    for f in raw.get("features", []):
        p = f["properties"]
        try:
            to = datetime.fromisoformat(p["todate"]).replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            to = now
        if str(p.get("iscurrent")).lower() != "true" and now - to > timedelta(days=5):
            continue
        lon, lat = f["geometry"]["coordinates"][:2]
        out.append({
            "id": str(p.get("eventid")),
            "type": p.get("eventtype"),
            "name": p.get("name"),
            "short": p.get("eventname") or p.get("name"),
            "level": str(p.get("alertlevel", "")).lower(),
            "lat": lat,
            "lon": lon,
        })
    return out
