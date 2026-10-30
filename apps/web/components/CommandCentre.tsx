"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, MotionConfig } from "motion/react";
import { fetchBot, fetchLevels, streamPlan, type BotInfo } from "@/lib/api";
import { ist } from "@/lib/format";
import type { AlertMessage, Levels, MapLayers, Place, SourceHealth, StepEvent, StepName } from "@/lib/types";
import MapView from "./MapView";
import Watchlist from "./Watchlist";
import IncidentPanel from "./IncidentPanel";
import CitizenPhone from "./CitizenPhone";
import JoinAlerts from "./JoinAlerts";

const SOURCES = ["Open-Meteo", "GloFAS", "SACHET", "GDACS", "RainViewer", "OSM", "Routing", "Telegram", "Sarvam"];
const REFRESH_MS = 5 * 60 * 1000;

type Health = Record<string, Pick<SourceHealth, "state" | "note">>;

export default function CommandCentre() {
  const [levels, setLevels] = useState<Levels | null>(null);
  const [levelsError, setLevelsError] = useState<string | null>(null);
  const [updated, setUpdated] = useState<Date | null>(null);
  const [health, setHealth] = useState<Health>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [focus, setFocus] = useState<{ lat: number; lon: number; key: number } | null>(null);
  const [steps, setSteps] = useState<Partial<Record<StepName, StepEvent>>>({});
  const [retries, setRetries] = useState(0);
  const [layers, setLayers] = useState<MapLayers>({});
  const [message, setMessage] = useState<AlertMessage | null>(null);
  const [origin, setOrigin] = useState<{ name: string; lat: number; lon: number } | null>(null);
  const [bot, setBot] = useState<BotInfo | null>(null);
  const [running, setRunning] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const [citizen, setCitizen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [clock, setClock] = useState("");
  const closeStream = useRef<(() => void) | null>(null);

  const mergeHealth = (src: Record<string, SourceHealth>) =>
    setHealth((h) => ({ ...h, ...Object.fromEntries(Object.entries(src).map(([k, v]) => [k, { state: v.state, note: v.note }])) }));

  const load = useCallback(async () => {
    try {
      const d = await fetchLevels();
      setLevels(d);
      setUpdated(new Date());
      setLevelsError(null);
      mergeHealth(d.sources);
      setSelected((s) => s ?? d.places[0]?.id ?? null);
    } catch {
      setLevelsError("Can't reach the RAHAT server. Retrying every 30 seconds.");
    }
  }, []);

  useEffect(() => {
    fetchBot().then(setBot).catch(() => setBot(null));
  }, []);
  useEffect(() => {
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => clearInterval(id);
  }, [load]);
  useEffect(() => {
    if (!levelsError) return;
    const id = setTimeout(load, 30_000);
    return () => clearTimeout(id);
  }, [levelsError, load]);
  useEffect(() => {
    const tick = () => setClock(`${ist(new Date())} IST`);
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 2400);
    return () => clearTimeout(id);
  }, [toast]);

  const place: Place | undefined = levels?.places.find((p) => p.id === selected);

  const resetPlan = () => {
    closeStream.current?.();
    setSteps({});
    setRetries(0);
    setLayers({});
    setMessage(null);
    setOrigin(null);
    setPlanError(null);
    setRunning(false);
  };

  const select = (id: string) => {
    if (id === selected) return;
    resetPlan();
    setSelected(id);
    const p = levels?.places.find((x) => x.id === id);
    if (p) setFocus({ lat: p.lat, lon: p.lon, key: Date.now() });
  };

  const run = (text: string) => {
    if (!place) return;
    resetPlan();
    setRunning(true);
    closeStream.current = streamPlan({ lat: place.lat, lon: place.lon, text: text.trim() || undefined }, (ev) => {
      switch (ev.type) {
        case "step":
          setSteps((s) => {
            if (ev.status === "run" && s[ev.step] && ev.step === "logistics") setRetries((r) => r + 1);
            return { ...s, [ev.step]: ev };
          });
          break;
        case "map":
          setLayers((l) => ({ ...l, [ev.layer]: ev.data }));
          break;
        case "result":
          setMessage(ev.message);
          setOrigin({ name: ev.place.name, lat: ev.place.lat, lon: ev.place.lon });
          break;
        case "error":
          setPlanError(ev.text);
          setRunning(false);
          break;
        case "done":
          mergeHealth(ev.sources);
          setRunning(false);
          break;
      }
    });
  };

  return (
    <MotionConfig reducedMotion="user">
      <header className="top">
        <div className="brand"><b>RAHAT</b><span lang="hi">राहत</span><i>Command centre · India</i></div>
        <div className="health" aria-label="Data source status">
          {SOURCES.map((n) => {
            const h = health[n];
            const s = h?.state ?? "wait";
            return <span key={n} className="chip" data-s={s} title={h?.note}>{n}{s === "fallback" ? " · fallback" : s === "down" ? " · down" : ""}</span>;
          })}
        </div>
        <div className="clock">{clock}</div>
        <JoinAlerts bot={bot} />
        <button className="toggle" aria-pressed={citizen} onClick={() => setCitizen((c) => !c)}>Citizen view</button>
      </header>

      <MapView
        places={levels?.places ?? []}
        sachet={levels?.sachet ?? []}
        gdacs={levels?.gdacs ?? []}
        layers={layers}
        focus={focus}
        onSelect={select}
        onRadar={(state, note) => setHealth((h) => ({ ...h, RainViewer: { state, note } }))}
      />

      <aside className="panel left" aria-label="Watchlist">
        <header>
          <span className="label">Watchlist · live levels</span>
          <span className="label">{updated ? `updated ${ist(updated)}` : "loading"}</span>
        </header>
        <div className="scroll">
          {levelsError && <div className="empty" role="alert">{levelsError}</div>}
          {!levels && !levelsError && <div className="empty">Reading rain, rivers, heat and official alerts…</div>}
          {levels && <Watchlist places={levels.places} selected={selected} onSelect={select} />}
        </div>
      </aside>

      <aside className="panel right" aria-label="Incident and response plan">
        <div className="scroll">
          {place ? (
            <IncidentPanel place={place} steps={steps} retries={retries} running={running} message={message} error={planError} origin={origin} bot={bot} onRun={run} />
          ) : (
            <div className="inc-head"><span className="label">Loading live data</span><h2>Reading the sky…</h2><p>Fetching rainfall, river discharge and official alerts.</p></div>
          )}
        </div>
      </aside>

      <AnimatePresence>
        {citizen && <CitizenPhone key="phone" message={message} placeName={place?.name ?? ""} driver={place?.driver?.text ?? null} onToast={setToast} />}
      </AnimatePresence>
      {toast && <div className="toast" role="status">{toast}</div>}
    </MotionConfig>
  );
}
