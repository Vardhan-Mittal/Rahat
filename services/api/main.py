import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from rahat import http, watchlist
from rahat.config import CORS_ORIGINS
from rahat.graph.build import run_plan

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("rahat")


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
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
