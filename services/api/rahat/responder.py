"""Runs the plan graph for one SOS and collects the outcome, with an optional per-step callback."""

import re
from collections.abc import Awaitable, Callable

from .graph.build import run_plan

StepCallback = Callable[[dict], Awaitable[None]]


def plain(html_text: str) -> str:
    return re.sub(r"<[^>]+>", "", html_text)


async def respond(text: str = "", lat: float | None = None, lon: float | None = None, lang: str | None = None,
                  on_step: StepCallback | None = None) -> dict:
    """Returns {"result": result event or None, "steps": [...], "halted": step event that stopped the plan or None}."""
    steps: list[dict] = []
    result = None
    async for ev in run_plan(text, lat, lon, lang):
        if ev["type"] == "step" and ev["status"] != "run":
            steps.append(ev)
            if on_step:
                await on_step(ev)
        elif ev["type"] == "result":
            result = ev
    halted = next((s for s in steps if s["step"] == "intake" and s["status"] == "fail"), None)
    return {"result": result, "steps": steps, "halted": halted}
