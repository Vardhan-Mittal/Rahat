"""Monitoring locations for the command centre and how their live levels are computed."""

import asyncio
import time

from . import hazards
from .sources import alerts, open_meteo

# Configuration (which places we watch), not data: every number about them is fetched live.
PLACES = [
    {"id": "ghy", "name": "Guwahati", "state": "Assam", "lat": 26.1800, "lon": 91.7470, "river": "Brahmaputra"},
    {"id": "bpt", "name": "Barpeta", "state": "Assam", "lat": 26.3200, "lon": 91.0000, "river": "Beki"},
    {"id": "pat", "name": "Patna", "state": "Bihar", "lat": 25.6100, "lon": 85.1400, "river": "Ganga"},
    {"id": "kkd", "name": "Kakinada", "state": "Andhra Pradesh", "lat": 16.9900, "lon": 82.2500, "river": "Godavari delta"},
    {"id": "vsk", "name": "Visakhapatnam", "state": "Andhra Pradesh", "lat": 17.6900, "lon": 83.2200},
    {"id": "bbs", "name": "Bhubaneswar", "state": "Odisha", "lat": 20.3000, "lon": 85.8200, "river": "Mahanadi"},
    {"id": "che", "name": "Chennai", "state": "Tamil Nadu", "lat": 13.0800, "lon": 80.2700},
    {"id": "koc", "name": "Kochi", "state": "Kerala", "lat": 9.9300, "lon": 76.2700},
    {"id": "bom", "name": "Mumbai", "state": "Maharashtra", "lat": 19.0700, "lon": 72.8800},
    {"id": "jai", "name": "Jaipur", "state": "Rajasthan", "lat": 26.9100, "lon": 75.7900},
    {"id": "del", "name": "Delhi", "state": "Delhi", "lat": 28.6100, "lon": 77.2100, "river": "Yamuna"},
]

_cache: dict = {"at": 0.0, "value": None}


async def levels(max_age: float = 300) -> dict:
    if _cache["value"] and time.monotonic() - _cache["at"] < max_age:
        return _cache["value"]

    pts = [(p["lat"], p["lon"]) for p in PLACES]
    fc, fl, sa, gd = await asyncio.gather(
        open_meteo.forecast(pts), open_meteo.flood(pts), alerts.sachet(), alerts.gdacs(), return_exceptions=True
    )
    sa_list = sa if isinstance(sa, list) else []
    gd_list = gd if isinstance(gd, list) else []

    out = []
    for i, p in enumerate(PLACES):
        rules = []
        f = fc[i] if isinstance(fc, list) else None
        q = fl[i] if isinstance(fl, list) else None
        if f:
            rules.append(hazards.rain_rule(f["rain24"]))
            if f["tmax3"] is not None:
                rules.append(hazards.heat_rule(f["tmax3"]))
        if q:
            rules.append(hazards.river_rule(q["peak3"], q["median"], p.get("river")))
        rules += hazards.official_rules(p["lat"], p["lon"], alerts.covering(sa_list, p["lat"], p["lon"]), gd_list)
        a = hazards.combine(rules)
        out.append({
            **p,
            **a,
            "rain24": f["rain24"] if f else None,
            "tmax": f["tmax3"] if f else None,
            "rain7": f["rain7"] if f else None,
            "ratio": round(q["peak3"] / q["median"], 2) if q and q["peak3"] and q["median"] and q["median"] >= 50 else None,
        })
    out.sort(key=lambda x: (hazards.RANK[x["level"]], x["rain24"] or 0), reverse=True)
    value = {"places": out, "sachet": sa_list, "gdacs": gd_list}
    _cache.update(at=time.monotonic(), value=value)
    return value
