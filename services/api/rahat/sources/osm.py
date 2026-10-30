"""OpenStreetMap: facilities via Overpass (two mirrors) with Nominatim as fallback, plus geocoding."""

import asyncio

from ..http import Timer, get_json, mark

OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
NOMINATIM = "https://nominatim.openstreetmap.org/search"


def _kind(amenity: str) -> str:
    return "hospital" if amenity in ("hospital", "clinic") else "school"


async def facilities(lat: float, lon: float, radius_m: int) -> tuple[list[dict], str]:
    """Hospitals, clinics, schools and colleges near a point. Returns (items, source used)."""
    q = (
        f'[out:json][timeout:15];('
        f'node["amenity"~"^(hospital|clinic|school|college)$"](around:{radius_m},{lat},{lon});'
        f'way["amenity"~"^(hospital|clinic|school|college)$"](around:{radius_m},{lat},{lon});'
        f');out center 120;'
    )
    with Timer() as t:
        # Race both mirrors; the first good answer wins.
        tasks = [asyncio.create_task(get_json(h, data={"data": q}, ttl=3600, timeout=7, retries=0)) for h in OVERPASS]
        data = None
        for fut in asyncio.as_completed(tasks):
            try:
                data = await fut
                break
            except Exception:
                continue
        for task in tasks:
            task.cancel()
        if data is not None:
            items = []
            for e in data.get("elements", []):
                tags = e.get("tags", {})
                la = e.get("lat") or e.get("center", {}).get("lat")
                lo = e.get("lon") or e.get("center", {}).get("lon")
                if la is None:
                    continue
                items.append({
                    "name": tags.get("name") or tags.get("name:en") or tags.get("amenity"),
                    "kind": _kind(tags.get("amenity", "")),
                    "lat": la,
                    "lon": lo,
                })
            mark("OSM", "live", "Overpass", t.elapsed)
            return items, "Overpass"

        # Overpass is often at capacity; Nominatim's amenity search is a slower but reliable fallback.
        d = radius_m / 111_000
        viewbox = f"{lon - d},{lat + d},{lon + d},{lat - d}"
        items: list[dict] = []
        for k in ("school", "hospital"):
            try:
                rows = await get_json(
                    NOMINATIM,
                    params={"q": k, "viewbox": viewbox, "bounded": 1, "format": "jsonv2", "limit": 40},
                    ttl=3600,
                )
                items += [{"name": r.get("name") or k, "kind": k, "lat": float(r["lat"]), "lon": float(r["lon"])} for r in rows]
            except Exception:
                pass
            await asyncio.sleep(1.1)  # Nominatim usage policy: max 1 request per second
    if not items:
        mark("OSM", "down", "Overpass and Nominatim failed", t.ms)
        raise RuntimeError("all facility sources failed")
    mark("OSM", "fallback", "Overpass busy, used Nominatim", t.ms)
    return items, "Nominatim"


async def geocode(text: str) -> dict | None:
    """Resolve a spoken/typed place name to coordinates, restricted to India."""
    rows = await get_json(
        NOMINATIM,
        params={"q": text, "countrycodes": "in", "format": "jsonv2", "limit": 1, "accept-language": "en"},
        ttl=86400,
    )
    if not rows:
        return None
    r = rows[0]
    return {"lat": float(r["lat"]), "lon": float(r["lon"]), "name": r.get("display_name", text).split(",")[0]}


async def reverse(lat: float, lon: float) -> str | None:
    try:
        r = await get_json(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 12, "accept-language": "en"},
            ttl=86400,
        )
        a = r.get("address", {})
        return a.get("city") or a.get("town") or a.get("village") or a.get("county") or a.get("state_district")
    except Exception:
        return None
