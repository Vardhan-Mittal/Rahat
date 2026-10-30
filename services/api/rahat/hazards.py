"""Deterministic hazard rules. The LLM never sets a level; these functions do.

Levels follow IMD's colour codes: green (no warning), yellow (be aware), orange (be prepared),
red (take action). "unknown" means critical data is missing and is never treated as safe.
"""

from .geo import km

RANK = {"unknown": -1, "green": 0, "yellow": 1, "orange": 2, "red": 3}
# Hazard-zone radius used for exposure and routing, by level.
ZONE_KM = {"red": 3.0, "orange": 2.0, "yellow": 1.2, "green": 0.8, "unknown": 1.0}


def _rule(level: str, text: str, why: str, source: str, kind: str = "official", value: float | str | None = None) -> dict:
    # kind/value let the alert template restate the driving number without free text.
    return {"level": level, "text": text, "why": why, "source": source, "kind": kind, "value": value}


def rain_rule(rain24: float) -> dict:
    # IMD 24-hour rainfall categories: heavy 64.5, very heavy 115.6, extremely heavy 204.5 mm.
    if rain24 >= 204.5:
        lv, why = "red", "≥ 204.5 mm · IMD extremely heavy rainfall"
    elif rain24 >= 115.6:
        lv, why = "orange", "≥ 115.6 mm · IMD very heavy rainfall"
    elif rain24 >= 64.5:
        lv, why = "yellow", "≥ 64.5 mm · IMD heavy rainfall"
    else:
        lv, why = "green", "below IMD heavy-rain threshold (64.5 mm)"
    return _rule(lv, f"Rain next 24 h: {rain24:.1f} mm", why, "Open-Meteo", "rain", round(rain24, 1))


def heat_rule(tmax: float, normal: float | None = None) -> dict:
    """IMD plains criteria when a 30-year normal is known; absolute thresholds otherwise."""
    if normal is not None:
        dep = tmax - normal
        if tmax >= 47 or (tmax >= 40 and dep >= 6.5):
            lv, why = "red", f"severe heatwave: departure +{dep:.1f} °C from 1991-2020 normal"
        elif tmax >= 45 or (tmax >= 40 and dep >= 4.5):
            lv, why = "orange", f"heatwave: departure +{dep:.1f} °C from normal {normal:.1f} °C"
        elif tmax >= 37 and dep >= 3:
            lv, why = "yellow", f"hot: +{dep:.1f} °C above normal {normal:.1f} °C"
        else:
            lv, why = "green", f"within heat criteria (normal {normal:.1f} °C)"
        return _rule(lv, f"Max temperature, 3 days: {tmax:.1f} °C", why, "Open-Meteo + archive", "heat", round(tmax, 1))
    if tmax >= 47:
        lv, why = "red", "≥ 47 °C · severe heatwave (absolute)"
    elif tmax >= 45:
        lv, why = "orange", "≥ 45 °C · heatwave (absolute)"
    elif tmax >= 40:
        lv, why = "yellow", "≥ 40 °C · watch for heatwave"
    else:
        lv, why = "green", "below heat thresholds"
    return _rule(lv, f"Max temperature, 3 days: {tmax:.1f} °C", why, "Open-Meteo", "heat", round(tmax, 1))


def river_rule(peak: float | None, median: float | None, river: str | None = None) -> dict:
    if peak is None or median is None or median < 50:
        return _rule("green", "No major river at this grid cell", f"median {median or 0:.0f} m³/s < 50, river rule skipped", "GloFAS", "river")
    ratio = peak / median
    if ratio >= 3:
        lv = "red"
    elif ratio >= 2:
        lv = "orange"
    elif ratio >= 1.5:
        lv = "yellow"
    else:
        lv = "green"
    why = f"≥ {dict(red=3, orange=2, yellow=1.5).get(lv)}× seasonal median" if lv != "green" else "within seasonal range"
    name = f"({river}) " if river else ""
    return _rule(lv, f"River discharge {name}{peak:.0f} m³/s, {ratio:.2f}× median", why, "GloFAS", "river", round(ratio, 1))


def official_rules(lat: float, lon: float, sachet_hits: list[dict], gdacs_events: list[dict]) -> list[dict]:
    """Official alerts can only raise a level, never lower it."""
    rules = []
    for a in sachet_hits:
        rules.append(_rule(a["level"], f"{a['type']} · {a['area']}", f"official alert from {a['source']} via NDMA SACHET", "SACHET", "official", a["type"]))
    for g in gdacs_events:
        d = km(lat, lon, g["lat"], g["lon"])
        if d < 350 and g["level"] in ("red", "orange"):
            lv = "orange" if g["level"] == "red" else "yellow"
            rules.append(_rule(lv, f"{g['name']}, {d:.0f} km away", f"GDACS {g['level']} alert within 350 km", "GDACS", "official", g["short"]))
    return rules


def combine(rules: list[dict]) -> dict:
    if not rules:
        return {"level": "unknown", "rules": [], "driver": None}
    driver = max(rules, key=lambda r: RANK[r["level"]])
    return {"level": driver["level"], "rules": rules, "driver": driver}
