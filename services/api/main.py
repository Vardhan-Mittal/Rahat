import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from rahat import bot, http, store, watchlist
from rahat.config import CORS_ORIGINS
from rahat.graph.build import run_plan

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("rahat")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await bot.start()
    yield
    await bot.stop()
    await http.close()


app = FastAPI(title="RAHAT API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["GET", "POST"], allow_headers=["*"])


@app.get("/api/health")
async def health():
    return {"ok": True, "sources": http.HEALTH}


@app.get("/api/levels")
async def levels():
    data = await watchlist.levels()
    return {**data, "sources": http.HEALTH}


@app.get("/api/plan")
async def plan(
    text: str = Query("", max_length=2000),
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    lang: str | None = Query(None, max_length=5),
):
    """Server-Sent Events stream of the response plan for one SOS."""

    async def events():
        try:
            async for ev in run_plan(text, lat, lon, lang):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception:
            log.exception("plan failed")
            yield 'data: {"type": "error", "text": "The plan stopped unexpectedly. An operator has been notified."}\n\n'
        yield f"data: {json.dumps({'type': 'done', 'sources': http.HEALTH})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- Telegram channel

@app.get("/api/bot")
async def bot_info():
    name = bot.username()
    return {"enabled": bot.enabled(), "username": name, "link": f"https://t.me/{name}" if name else None}


@app.get("/api/recipients")
async def recipients(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180),
                     radius_km: float = Query(..., gt=0, le=100)):
    return {"count": len(await store.users_within(lat, lon, radius_km))}


class Shelter(BaseModel):
    name: str = Field(max_length=200)
    lat: float
    lon: float


class AlertBody(BaseModel):
    place: str = Field(max_length=200)
    level: str = Field(pattern="^(green|yellow|orange|red|unknown)$")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radius_km: float = Field(gt=0, le=100)
    hi: str = Field(max_length=1500)
    en: str = Field(max_length=1500)
    local: str | None = Field(None, max_length=1500)
    lang: str = Field("hi", max_length=5)
    shelter: Shelter | None = None


@app.post("/api/broadcast")
async def broadcast(body: AlertBody):
    """Operator-approved zone alert: sends to every opted-in person inside the radius."""
    if not bot.enabled():
        raise HTTPException(503, "Telegram bot is not configured on the server.")
    msg = {"hi": body.hi, "en": body.en, "local": body.local, "lang": body.lang,
           "shelter": body.shelter.model_dump() if body.shelter else None}
    return await bot.broadcast(body.place, body.level, body.lat, body.lon, body.radius_km, msg)


@app.get("/api/funnel")
async def funnel(alert_id: int | None = None):
    return await store.funnel(alert_id)


@app.get("/api/sos")
async def sos(limit: int = Query(20, ge=1, le=100)):
    return {"items": await store.recent_sos(limit)}
