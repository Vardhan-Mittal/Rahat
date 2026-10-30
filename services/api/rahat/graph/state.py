from typing import TypedDict


class PlanState(TypedDict, total=False):
    # input
    sos_text: str
    lat: float | None
    lon: float | None
    lang: str | None
    # intake
    intake: dict
    place: dict  # {lat, lon, name, how}
    halt: bool
    # sentinel
    assessment: dict  # {level, rules, driver}
    zone_km: float
    # impact
    facilities: list[dict]
    candidates: list[dict]
    origin_elev: float | None
    # logistics / verifier
    shelter: dict | None
    route: dict | None
    rejected: list[str]
    retries: int
    route_ok: bool
    retry: bool
    # comms
    message: dict
