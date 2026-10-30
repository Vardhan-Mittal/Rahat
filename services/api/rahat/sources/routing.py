"""Routing: OSM foot router first, public OSRM driving as fallback."""

from ..http import Timer, get_json, mark

ROUTERS = [
    ("walk", "OSM foot router", "https://routing.openstreetmap.de/routed-foot/route/v1/foot/"),
    ("drive", "OSRM driving", "https://router.project-osrm.org/route/v1/driving/"),
]


async def route(a: tuple[float, float], b: tuple[float, float]) -> dict | None:
    """a, b are (lat, lon). Returns {mode, via, distance_m, duration_s, coords} or None if every router failed."""
    with Timer() as t:
        for i, (mode, via, base) in enumerate(ROUTERS):
            url = f"{base}{a[1]:.6f},{a[0]:.6f};{b[1]:.6f},{b[0]:.6f}"
            try:
                d = await get_json(url, params={"overview": "full", "geometries": "geojson"}, timeout=10, retries=0)
                if d.get("code") != "Ok":
                    continue
                r = d["routes"][0]
                mark("Routing", "live" if i == 0 else "fallback", via, t.elapsed)
                return {
                    "mode": mode,
                    "via": via,
                    "fallback": i > 0,
                    "distance_m": round(r["distance"]),
                    "duration_s": round(r["duration"]),
                    "coords": r["geometry"]["coordinates"],
                }
            except Exception:
                continue
    mark("Routing", "down", "all routers failed", t.ms)
    return None
