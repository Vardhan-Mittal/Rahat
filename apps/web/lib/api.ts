import type { Levels, PlanEvent } from "./types";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function fetchLevels(signal?: AbortSignal): Promise<Levels> {
  const r = await fetch(`${API}/api/levels`, { signal, cache: "no-store" });
  if (!r.ok) throw new Error(`Levels request failed (${r.status})`);
  return r.json();
}

/** Opens the plan event stream. Returns a function that closes it. */
export function streamPlan(
  params: { lat?: number; lon?: number; text?: string; lang?: string },
  onEvent: (e: PlanEvent) => void,
): () => void {
  const q = new URLSearchParams();
  if (params.lat != null) q.set("lat", params.lat.toFixed(5));
  if (params.lon != null) q.set("lon", params.lon.toFixed(5));
  if (params.text) q.set("text", params.text);
  if (params.lang) q.set("lang", params.lang);
  const es = new EventSource(`${API}/api/plan?${q}`);
  es.onmessage = (m) => {
    const ev = JSON.parse(m.data) as PlanEvent;
    onEvent(ev);
    if (ev.type === "done") es.close();
  };
  es.onerror = () => {
    if (es.readyState !== EventSource.CLOSED) {
      onEvent({ type: "error", text: "Lost connection to the RAHAT server. Check that the API is running." });
    }
    es.close();
  };
  return () => es.close();
}
