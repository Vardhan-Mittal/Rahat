import type { Levels, PlanEvent } from "./types";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8787";

export async function fetchLevels(signal?: AbortSignal): Promise<Levels> {
  const r = await fetch(`${API}/api/levels`, { signal, cache: "no-store" });
  if (!r.ok) throw new Error(`Levels request failed (${r.status})`);
  return r.json();
}

export interface BotInfo { enabled: boolean; username: string | null; link: string | null }
export interface Funnel {
  alert: { id: number; place: string; level: string; created: number } | null;
  alerted: number; heard: number; safe: number; help: number; failed: number;
}

async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path} failed (${r.status})`);
  return r.json();
}

export const fetchBot = () => getJSON<BotInfo>("/api/bot");
export const fetchFunnel = () => getJSON<Funnel>("/api/funnel");
export const fetchRecipients = (lat: number, lon: number, radius: number) =>
  getJSON<{ count: number }>(`/api/recipients?lat=${lat}&lon=${lon}&radius_km=${radius}`);

export async function sendBroadcast(body: Record<string, unknown>): Promise<{ alert_id: number; recipients: number; sent: number }> {
  const r = await fetch(`${API}/api/broadcast`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? `Sending failed (${r.status})`);
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
