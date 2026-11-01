"""Open-Meteo: forecast, GloFAS river discharge, elevation and the historical archive. No key needed.

Forecast and elevation fall back to MET Norway and OpenTopoData when Open-Meteo refuses (e.g. HTTP 429).
"""

import asyncio
from datetime import date, datetime, timedelta, timezone

from ..http import Timer, get_json, mark

IST_OFFSET = timedelta(hours=5, minutes=30)
MET_NO = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
OPENTOPO = "https://api.opentopodata.org/v1/srtm90m"
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
            # Shared cloud IPs often hit Open-Meteo's free per-IP quota (HTTP 429); MET Norway covers India too.
            try:
                out = await asyncio.gather(*(_met_no(lat, lon) for lat, lon in points))
            except Exception as e2:
                mark("Open-Meteo", "down", f"{e}; MET Norway: {e2}")
                raise e
            mark("Open-Meteo", "fallback", f"{e} → MET Norway", t.elapsed)
            return list(out)
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
            "source": "Open-Meteo",
        })
    return out


_met_no_limit = asyncio.Semaphore(4)


async def _met_no(lat: float, lon: float) -> dict:
    """Same shape as an Open-Meteo forecast row, built from MET Norway's hourly/6-hourly series."""
    async with _met_no_limit:
        d = await get_json(MET_NO, params={"lat": f"{lat:.3f}", "lon": f"{lon:.3f}"}, ttl=900)
    now = datetime.now(timezone.utc)
    rain24, tmax3 = 0.0, None
    rain_by_day: dict[str, float] = {}
    tmax_by_day: dict[str, float] = {}
    covered = now
    for step in d["properties"]["timeseries"]:
        ts = datetime.fromisoformat(step["time"].replace("Z", "+00:00"))
        data = step["data"]
        temp = data["instant"]["details"].get("air_temperature")
        day = (ts + IST_OFFSET).date().isoformat()
        if temp is not None:
            tmax_by_day[day] = max(tmax_by_day.get(day, temp), temp)
            if ts <= now + timedelta(hours=72):
                tmax3 = temp if tmax3 is None else max(tmax3, temp)
        # Count each hour once: 1-hour amounts where given, else 6-hour amounts (later in the forecast).
        if ts < covered:
            continue
        for key, hours in (("next_1_hours", 1), ("next_6_hours", 6)):
            amount = data.get(key, {}).get("details", {}).get("precipitation_amount")
            if amount is not None:
                rain_by_day[day] = rain_by_day.get(day, 0.0) + amount
                if ts < now + timedelta(hours=24):
                    rain24 += amount
                covered = ts + timedelta(hours=hours)
                break
    days = sorted(rain_by_day)[:7]
    return {
        "rain24": round(rain24, 1),
        "tmax3": tmax3,
        "days": days,
        "rain7": [round(rain_by_day[x], 1) for x in days],
        "tmax7": [tmax_by_day.get(x) for x in days],
        "source": "MET Norway",
    }


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
        try:
            data = await get_json(ELEVATION, params=_coords(chunk), ttl=86400)
            out.extend(data.get("elevation", [None] * len(chunk)))
        except Exception:
            # Fallback: OpenTopoData (SRTM 90 m), same 100-point batch limit.
            locs = "|".join(f"{lat:.5f},{lon:.5f}" for lat, lon in chunk)
            data = await get_json(OPENTOPO, params={"locations": locs}, ttl=86400, timeout=15)
            out.extend(r.get("elevation") for r in data.get("results", []))
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
