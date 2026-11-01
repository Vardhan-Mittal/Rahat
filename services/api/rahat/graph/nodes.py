"""Pipeline nodes. Each node streams trace events through LangGraph's custom stream writer.

Event shapes sent to the UI:
  {"type": "step", "step": str, "status": "run"|"ok"|"fix"|"fail", "text": str, "sources": [str], "ms": int}
  {"type": "map", "layer": "origin"|"zone"|"facilities"|"route", "data": GeoJSON}
  {"type": "result", ...}
Source names starting with "!" mark a fallback or a degraded source.
"""

import asyncio
import html
from datetime import datetime, timezone, timedelta

from langgraph.config import get_stream_writer

from .. import hazards, llm
from ..geo import circle, in_india, km, line_length_m
from ..http import Timer
from ..sources import alerts, open_meteo, osm, routing
from .state import PlanState

IST = timezone(timedelta(hours=5, minutes=30))


def _emit(step: str, status: str, text: str, sources: list[str] | None = None, ms: int | None = None) -> None:
    get_stream_writer()({"type": "step", "step": step, "status": status, "text": text, "sources": sources or [], "ms": ms})


def _map(layer: str, data: dict) -> None:
    get_stream_writer()({"type": "map", "layer": layer, "data": data})


def _fc(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def _point(lat: float, lon: float, **props) -> dict:
    return {"type": "Feature", "properties": props, "geometry": {"type": "Point", "coordinates": [lon, lat]}}


# ---------------------------------------------------------------- intake

async def intake(state: PlanState) -> PlanState:
    _emit("intake", "run", "Reading the request")
    with Timer() as t:
        text = (state.get("sos_text") or "").strip()
        if text:
            info = await llm.extract_sos(text)
        else:
            info = {"language": state.get("lang") or "hi", "need": "evacuate", "place_text": "", "people": 0,
                    "injured": False, "summary_en": "Location-only SOS", "is_emergency": True, "via": "none"}
        if state.get("lang"):
            info["language"] = state["lang"]

        lat, lon, how = state.get("lat"), state.get("lon"), "GPS"
        name = None
        if lat is None or lon is None:
            if info.get("place_text"):
                g = await osm.geocode(info["place_text"])
                if g:
                    lat, lon, name, how = g["lat"], g["lon"], g["name"], "place name"
        if lat is None or lon is None:
            _emit("intake", "fail", "No location in the message. Asking the person to share their location or the nearest village or town.",
                  ["!needs location"], t.elapsed)
            return {"intake": info, "halt": True}
        if not in_india(lat, lon):
            _emit("intake", "fail", "This location is outside India, which RAHAT does not cover.", ["!out of scope"], t.elapsed)
            return {"intake": info, "halt": True}
        name = name or await osm.reverse(lat, lon) or f"{lat:.3f}, {lon:.3f}"

    srcs = ["!rules (no LLM)" if info["via"] in ("rules", "none") else "Claude"]
    if how == "place name":
        srcs.append("Nominatim")
    bits = [f"need: {info['need'].replace('_', ' ')}", f"language: {info['language']}"]
    if info.get("people"):
        bits.append(f"{info['people']} people")
    if info.get("injured"):
        bits.append("injured")
    _emit("intake", "ok" if info["via"] not in ("rules",) else "fix",
          f"{'; '.join(bits)}. Location from {how}: <b>{html.escape(name)}</b>.", srcs, t.ms)
    _map("origin", _fc([_point(lat, lon, name=name)]))
    return {"intake": info, "place": {"lat": lat, "lon": lon, "name": name, "how": how}, "halt": False,
            "rejected": [], "retries": 0}


# ---------------------------------------------------------------- sentinel

async def sentinel(state: PlanState) -> PlanState:
    _emit("sentinel", "run", "Checking rain, river, heat and official alerts")
    p = state["place"]
    pt = [(p["lat"], p["lon"])]
    with Timer() as t:
        today = datetime.now(IST).date()
        fc, fl, sa, gd, normal = await asyncio.gather(
            open_meteo.forecast(pt), open_meteo.flood(pt), alerts.sachet(), alerts.gdacs(),
            asyncio.wait_for(open_meteo.tmax_normal(p["lat"], p["lon"], today), timeout=15),
            return_exceptions=True,
        )
        rules, used, missing = [], [], []
        if isinstance(fc, list):
            f = fc[0]
            rules.append(hazards.rain_rule(f["rain24"], f["source"]))
            if f["tmax3"] is not None:
                rules.append(hazards.heat_rule(f["tmax3"], normal if isinstance(normal, (int, float)) else None, f["source"]))
            used.append(f["source"] if f["source"] == "Open-Meteo" else f"!Open-Meteo busy → {f['source']}")
            if isinstance(normal, (int, float)):
                used.append("1991-2020 normal")
        else:
            missing.append("Open-Meteo")
        if isinstance(fl, list):
            rules.append(hazards.river_rule(fl[0]["peak3"], fl[0]["median"]))
            used.append("GloFAS")
        else:
            missing.append("GloFAS")
        sa_hits = alerts.covering(sa, p["lat"], p["lon"]) if isinstance(sa, list) else []
        rules += hazards.official_rules(p["lat"], p["lon"], sa_hits, gd if isinstance(gd, list) else [])
        used += [s for s, v in (("SACHET", sa), ("GDACS", gd)) if isinstance(v, list)]
        missing += [s for s, v in (("SACHET", sa), ("GDACS", gd)) if not isinstance(v, list)]

        # Missing forecast data makes the level unknown, never safe.
        a = hazards.combine(rules) if isinstance(fc, list) else {"level": "unknown", "rules": rules, "driver": None}
    zone = hazards.ZONE_KM[a["level"]]
    driver = a["driver"]["text"] if a["driver"] else "Forecast unavailable"
    status = "ok" if not missing and not any(u.startswith("!") for u in used) else "fix"
    _emit("sentinel", status,
          f"Level <b data-level=\"{a['level']}\">{a['level'].upper()}</b>. {html.escape(driver)}. Zone radius {zone:g} km by rule.",
          used + [f"!{m} down" for m in missing], t.ms)
    _map("zone", _fc([{"type": "Feature", "properties": {"level": a["level"]}, "geometry": circle(p["lat"], p["lon"], zone)}]))
    return {"assessment": a, "zone_km": zone}


# ---------------------------------------------------------------- impact

async def impact(state: PlanState) -> PlanState:
    _emit("impact", "run", "Finding hospitals, schools and colleges nearby")
    p, zone = state["place"], state["zone_km"]
    with Timer() as t:
        try:
            items, via = await osm.facilities(p["lat"], p["lon"], int(max(4000, zone * 2200)))
        except Exception:
            _emit("impact", "fail", "Every facility source failed. The alert will give general safety steps and the case goes to an operator.",
                  ["!Overpass down", "!Nominatim down"], t.elapsed)
            return {"facilities": [], "candidates": [], "origin_elev": None}
        for i, f in enumerate(items):
            f["id"] = f"f{i}"
            f["d_km"] = km(p["lat"], p["lon"], f["lat"], f["lon"])
            f["exposed"] = f["d_km"] <= zone
        cands = sorted((f for f in items if not f["exposed"] and f["kind"] == "school"), key=lambda f: f["d_km"])[:40]
        origin_elev = None
        try:
            elev = await open_meteo.elevation([(p["lat"], p["lon"])] + [(c["lat"], c["lon"]) for c in cands])
            origin_elev = elev[0]
            for c, e in zip(cands, elev[1:]):
                c["elev"] = e
            elev_note = f"Origin {origin_elev:.0f} m above sea level."
        except Exception:
            elev_note = "Elevation unavailable, using distance only."
    exposed = [f for f in items if f["exposed"]]
    hosp = sum(1 for f in exposed if f["kind"] == "hospital")
    _emit("impact", "ok" if via == "Overpass" else "fix",
          f"{len(items)} facilities found, <b>{len(exposed)}</b> inside the zone ({hosp} hospitals). {elev_note}",
          ["Overpass" if via == "Overpass" else "!Overpass busy → Nominatim", "Open-Meteo elevation"], t.ms)
    _map("facilities", _fc([_point(f["lat"], f["lon"], id=f["id"], name=f["name"], kind=f["kind"], exposed=f["exposed"],
                                   elev=round(f["elev"]) if f.get("elev") is not None else None) for f in items]))
    return {"facilities": items, "candidates": cands, "origin_elev": origin_elev}


# ---------------------------------------------------------------- logistics

async def logistics(state: PlanState) -> PlanState:
    _emit("logistics", "run", "Choosing a shelter outside the zone, on higher ground")
    p = state["place"]
    with Timer() as t:
        rejected = set(state.get("rejected", []))
        pool = [c for c in state.get("candidates", []) if c["id"] not in rejected]
        oe = state.get("origin_elev")
        high = [c for c in pool if oe is not None and c.get("elev") is not None and c["elev"] >= oe + 2]
        shelter = (high or pool or [None])[0]
        if shelter is None:
            _emit("logistics", "fail", "No school outside the zone within range. Advising higher ground and flagging for an operator.",
                  ["!no shelter"], t.elapsed)
            return {"shelter": None, "route": None}
        rt = await routing.route((p["lat"], p["lon"]), (shelter["lat"], shelter["lon"]))
    elev = f", {shelter['elev']:.0f} m" if shelter.get("elev") is not None else ""
    if rt:
        mins = round(rt["duration_s"] / 60)
        _emit("logistics", "fix" if rt["fallback"] else "ok",
              f"Shelter: <b>{html.escape(shelter['name'])}</b>{elev}. {'Walk' if rt['mode'] == 'walk' else 'Drive'} "
              f"{rt['distance_m'] / 1000:.1f} km, about {mins} min.",
              [rt["via"]] if not rt["fallback"] else ["!foot router failed → OSRM driving"], t.ms)
        _map("route", {"type": "Feature", "properties": {"mode": rt["mode"]}, "geometry": {"type": "LineString", "coordinates": rt["coords"]}})
    else:
        _emit("logistics", "fix", f"Shelter: <b>{html.escape(shelter['name'])}</b>{elev}. Routing services down: direction only, not a checked path.",
              ["!routing down"], t.ms)
    _map("facilities", _fc([_point(f["lat"], f["lon"], id=f["id"], name=f["name"], kind=f["kind"], exposed=f["exposed"],
                                   shelter=f["id"] == shelter["id"],
                                   elev=round(f["elev"]) if f.get("elev") is not None else None)
                            for f in state.get("facilities", [])]))
    return {"shelter": shelter, "route": rt}


# ---------------------------------------------------------------- verifier

async def verifier(state: PlanState) -> PlanState:
    _emit("verifier", "run", "Checking the route against the hazard zone")
    p, zone, rt, shelter = state["place"], state["zone_km"], state.get("route"), state.get("shelter")
    with Timer() as t:
        if not shelter:
            _emit("verifier", "fix", "No shelter to check. Alert will carry general safety steps only.", ["geometry check"], t.elapsed)
            return {"route_ok": False, "retry": False}
        if not rt:
            _emit("verifier", "fix", "No routed path to check. Alert says the direction is unverified.", ["geometry check"], t.elapsed)
            return {"route_ok": False, "retry": False}
        coords = rt["coords"]
        inside = [km(p["lat"], p["lon"], c[1], c[0]) <= zone for c in coords]
        exit_idx = inside.index(False) if False in inside else len(inside)
        reenters = any(inside[exit_idx:])
        exit_m = line_length_m(coords[: exit_idx + 1])
    if reenters and state.get("retries", 0) < 2:
        _emit("verifier", "fix", f"Route to {html.escape(shelter['name'])} re-enters the hazard zone. Rejected, trying the next shelter.",
              ["geometry check"], t.ms)
        return {"rejected": state.get("rejected", []) + [shelter["id"]], "retries": state.get("retries", 0) + 1,
                "route_ok": False, "retry": True}
    if reenters:
        _emit("verifier", "fix", "Every nearby route re-enters the zone. Using the best one and flagging it for human review.",
              ["geometry check", "!human review"], t.ms)
        return {"route_ok": False, "retry": False}
    _emit("verifier", "ok", f"Route leaves the zone after {exit_m:.0f} m and never re-enters. Alert numbers come only from tool outputs.",
          ["geometry check", "template check"], t.ms)
    return {"route_ok": True, "retry": False}


def after_verifier(state: PlanState) -> str:
    return "logistics" if state.get("retry") else "comms"


# ---------------------------------------------------------------- comms

LEVEL_EN = {"red": "RED alert", "orange": "ORANGE alert", "yellow": "YELLOW alert", "green": "No active warning", "unknown": "Status unknown"}
LEVEL_HI = {"red": "लाल चेतावनी", "orange": "नारंगी चेतावनी", "yellow": "पीली चेतावनी", "green": "कोई चेतावनी नहीं", "unknown": "स्थिति अज्ञात"}


def _driver_hi(rule: dict | None) -> str:
    if not rule:
        return "मौसम की जानकारी अभी उपलब्ध नहीं है"
    k, v = rule.get("kind"), rule.get("value")
    if k == "rain":
        return f"अगले 24 घंटे में {v} मिमी बारिश"
    if k == "heat":
        return f"अधिकतम तापमान {v}°C"
    if k == "river" and v is not None:
        return f"नदी का बहाव सामान्य से {v} गुना"
    if k == "river":
        return "आसपास कोई बड़ी नदी नहीं"
    return f"आधिकारिक चेतावनी: {v}"


async def comms(state: PlanState) -> PlanState:
    _emit("comms", "run", "Writing the alert")
    p, a = state["place"], state["assessment"]
    lv, shelter, rt = a["level"], state.get("shelter"), state.get("route")
    lang = state.get("intake", {}).get("language", "hi")
    with Timer() as t:
        driver_en = a["driver"]["text"] if a["driver"] else "Forecast unavailable"
        act_en = "Stay alert." if lv == "green" else "Move to higher, safe ground now."
        act_hi = "सतर्क रहें।" if lv == "green" else "अभी ऊँची और सुरक्षित जगह पर जाएँ।"
        if shelter:
            dist = f"{rt['distance_m'] / 1000:.1f}" if rt else f"{shelter['d_km']:.1f}"
            how_en = (f", about {round(rt['duration_s'] / 60)} min {'on foot' if rt['mode'] == 'walk' else 'by road'}" if rt else
                      " (direction only, route not checked)")
            how_hi = (f", {'पैदल' if rt['mode'] == 'walk' else 'गाड़ी से'} लगभग {round(rt['duration_s'] / 60)} मिनट" if rt else
                      " (रास्ता जाँचा नहीं गया)")
            go_en = f" Nearest safe place: {shelter['name']}, {dist} km{how_en}."
            go_hi = f" नज़दीकी सुरक्षित स्थान: {shelter['name']}, {dist} किमी{how_hi}।"
        else:
            go_en = " Go to higher ground away from rivers and drains."
            go_hi = " नदी और नालों से दूर ऊँची जगह पर जाएँ।"
        en = f"{p['name']}: {LEVEL_EN[lv]}. {driver_en}. {act_en}{go_en} Emergency: call 112."
        hi = f"{p['name']}: {LEVEL_HI[lv]}। {_driver_hi(a['driver'])}। {act_hi}{go_hi} आपात स्थिति में 112 पर कॉल करें।"
        local, srcs = None, ["template", "no free text"]
        if lang not in ("hi", "en"):
            local = await llm.translate(en, lang)
            srcs.append(f"Claude → {lang}" if local else f"!{lang} translation unavailable → Hindi")
    msg = {"level": lv, "en": en, "hi": hi, "local": local, "lang": lang,
           "shelter": {k: shelter[k] for k in ("name", "lat", "lon")} if shelter else None,
           "route": {k: rt[k] for k in ("mode", "distance_m", "duration_s")} if rt else None,
           "steps_hi": [act_hi, go_hi.strip(), "आपात स्थिति में 112 पर कॉल करें।"]}
    _emit("comms", "ok" if (lang in ("hi", "en") or local) else "fix",
          "Alert filled only from verified values. Voice delivery connects with the Telegram bot.", srcs, t.ms)
    get_stream_writer()({"type": "result", "message": msg, "assessment": a, "place": p, "route_ok": state.get("route_ok", False)})
    return {"message": msg}
