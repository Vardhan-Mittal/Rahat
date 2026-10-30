from langgraph.graph import END, START, StateGraph

from . import nodes
from .state import PlanState


def build():
    g = StateGraph(PlanState)
    g.add_node("intake", nodes.intake)
    g.add_node("sentinel", nodes.sentinel)
    g.add_node("impact", nodes.impact)
    g.add_node("logistics", nodes.logistics)
    g.add_node("verifier", nodes.verifier)
    g.add_node("comms", nodes.comms)

    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", lambda s: END if s.get("halt") else "sentinel", ["sentinel", END])
    g.add_edge("sentinel", "impact")
    g.add_conditional_edges("impact", lambda s: "logistics" if s.get("candidates") else "comms", ["logistics", "comms"])
    g.add_edge("logistics", "verifier")
    g.add_conditional_edges("verifier", nodes.after_verifier, ["logistics", "comms"])
    g.add_edge("comms", END)
    return g.compile()


GRAPH = build()


async def run_plan(sos_text: str = "", lat: float | None = None, lon: float | None = None, lang: str | None = None):
    """Yield the custom trace/map/result events as the graph runs."""
    async for event in GRAPH.astream(
        {"sos_text": sos_text, "lat": lat, "lon": lon, "lang": lang},
        stream_mode="custom",
    ):
        yield event
