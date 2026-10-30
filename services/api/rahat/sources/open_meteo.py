"""Open-Meteo: forecast, GloFAS river discharge, elevation and the historical archive. No key needed."""

from datetime import date

from ..http import Timer, get_json, mark

FORECAST = "https://api.open-meteo.com/v1/forecast"
FLOOD = "https://flood-api.open-meteo.com/v1/flood"
ELEVATION = "https://api.open-meteo.com/v1/elevation"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"


def _coords(points: list[tuple[float, float]]) -> dict:
    return {
        "latitude": ",".join(f"{p[0]:.4f}" for p in points),
        "longitude": ",".join(f"{p[1]:.4f}" for p in points),
    }


def _as_list(value) -> list:
    return value if isinstance(value, list) else [value]


async def forecast(points: list[tuple[float, float]]) -> list[dict]:
    """Per point: rain over the next 24 h, max temperature over 3 days, 7-day daily series."""
    params = {
        **_coords(points),
        "hourly": "precipitation",
        "forecast_hours": 24,
        "daily": "precipitation_sum,temperature_2m_max",
        "forecast_days": 7,
        "timezone": "Asia/Kolkata",
    }
    with Timer() as t:
        try:
            raw = _as_list(await get_json(FORECAST, params=params, ttl=600))
        except Exception as e:
            mark("Open-Meteo", "down", str(e))
            raise
    mark("Open-Meteo", "live", f"{len(points)} points", t.elapsed)
    out = []
    for r in raw:
        tmax = [v for v in r["daily"]["temperature_2m_max"][:3] if v is not None]
        out.append({
            "rain24": round(sum(v or 0 for v in r["hourly"]["precipitation"]), 1),
            "tmax3": max(tmax) if tmax else None,
            "days": r["daily"]["time"],
            "rain7": r["daily"]["precipitation_sum"],
            "tmax7": r["daily"]["temperature_2m_max"],
        })
    return out


async def flood(points: list[tuple[float, float]]) -> list[dict]:
    """Per point: GloFAS discharge peak over 3 days vs. today's seasonal median."""
    params = {**_coords(points), "daily": "river_discharge,river_discharge_median", "forecast_days": 7}
    with Timer() as t:
        try:
            raw = _as_list(await get_json(FLOOD, params=params, ttl=1800))
        except Exception as e:
            mark("GloFAS", "down", str(e))
            raise
    mark("GloFAS", "live", f"{len(points)} points", t.elapsed)
    out = []
    for r in raw:
        q = r["daily"]["river_discharge"]
        med = r["daily"]["river_discharge_median"][0]
        peak = max((v for v in q[:3] if v is not None), default=None)
        out.append({"q7": q, "median": med, "peak3": peak})
    return out


async def elevation(points: list[tuple[float, float]]) -> list[float | None]:
    out: list[float | None] = []
    for i in range(0, len(points), 100):
        chunk = points[i : i + 100]
        data = await get_json(ELEVATION, params=_coords(chunk), ttl=86400)
        out.extend(data.get("elevation", [None] * len(chunk)))
    return out


async def tmax_normal(lat: float, lon: float, day: date, window: int = 3) -> float | None:
    """1991-2020 mean of daily max temperature within ±window days of `day` (IMD uses 30-year normals)."""
    params = {
        "latitude": f"{lat:.3f}",
        "longitude": f"{lon:.3f}",
        "start_date": "1991-01-01",
        "end_date": "2020-12-31",
        "daily": "temperature_2m_max",
        "timezone": "Asia/Kolkata",
    }
    data = await get_json(ARCHIVE, params=params, ttl=86400, timeout=25)
    target = day.timetuple().tm_yday
    vals = []
    for t, v in zip(data["daily"]["time"], data["daily"]["temperature_2m_max"]):
        if v is None:
            continue
        d = date.fromisoformat(t).timetuple().tm_yday
        if min(abs(d - target), 366 - abs(d - target)) <= window:
            vals.append(v)
    return round(sum(vals) / len(vals), 1) if vals else None
