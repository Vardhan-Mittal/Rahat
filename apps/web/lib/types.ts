export type Level = "green" | "yellow" | "orange" | "red" | "unknown";

export interface Rule {
  level: Level;
  text: string;
  why: string;
  source: string;
  kind?: string;
  value?: number | string | null;
}

export interface Place {
  id: string;
  name: string;
  state: string;
  lat: number;
  lon: number;
  river?: string;
  level: Level;
  rules: Rule[];
  driver: Rule | null;
  rain24: number | null;
  tmax: number | null;
  rain7: number[] | null;
  ratio: number | null;
}

export interface SachetAlert {
  id: string;
  type: string;
  area: string;
  source: string;
  level: Level;
  message: string;
  lat: number;
  lon: number;
  radius_km: number;
}

export interface GdacsEvent {
  id: string;
  type: string;
  name: string;
  short: string;
  level: string;
  lat: number;
  lon: number;
}

export interface SourceHealth {
  state: "live" | "fallback" | "down";
  note: string;
  ms: number | null;
  at: string;
}

export interface Levels {
  places: Place[];
  sachet: SachetAlert[];
  gdacs: GdacsEvent[];
  sources: Record<string, SourceHealth>;
}

export const STEPS = ["intake", "sentinel", "impact", "logistics", "verifier", "comms"] as const;
export type StepName = (typeof STEPS)[number];
export type StepStatus = "idle" | "run" | "ok" | "fix" | "fail";

export interface StepEvent {
  type: "step";
  step: StepName;
  status: Exclude<StepStatus, "idle">;
  text: string;
  sources: string[];
  ms: number | null;
}

export interface MapEvent {
  type: "map";
  layer: "origin" | "zone" | "facilities" | "route";
  data: GeoJSON.FeatureCollection | GeoJSON.Feature;
}

export interface AlertMessage {
  level: Level;
  en: string;
  hi: string;
  local: string | null;
  lang: string;
  shelter: { name: string; lat: number; lon: number } | null;
  route: { mode: "walk" | "drive"; distance_m: number; duration_s: number } | null;
  steps_hi: string[];
}

export interface ResultEvent {
  type: "result";
  message: AlertMessage;
  assessment: { level: Level; rules: Rule[]; driver: Rule | null };
  place: { lat: number; lon: number; name: string; how: string };
  route_ok: boolean;
}

export type PlanEvent =
  | StepEvent
  | MapEvent
  | ResultEvent
  | { type: "error"; text: string }
  | { type: "done"; sources: Record<string, SourceHealth> };

export type MapLayers = Partial<Record<MapEvent["layer"], MapEvent["data"]>>;
