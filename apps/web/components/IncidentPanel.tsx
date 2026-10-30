"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import type { AlertMessage, Place, StepEvent, StepName, StepStatus } from "@/lib/types";
import { STEPS } from "@/lib/types";
import { LEVEL_COLOR, ZONE_KM, fmt, ist } from "@/lib/format";
import Gauge from "./Gauge";
import HeardFunnel from "./HeardFunnel";
import BroadcastBox from "./BroadcastBox";
import type { BotInfo } from "@/lib/api";

const STEP_LABEL: Record<StepName, string> = {
  intake: "Intake", sentinel: "Sentinel", impact: "Impact", logistics: "Logistics", verifier: "Verifier", comms: "Comms",
};

type Props = {
  place: Place;
  steps: Partial<Record<StepName, StepEvent>>;
  retries: number;
  running: boolean;
  message: AlertMessage | null;
  error: string | null;
  origin: { name: string; lat: number; lon: number } | null;
  bot: BotInfo | null;
  onRun: (text: string) => void;
};

export default function IncidentPanel({ place, steps, retries, running, message, error, origin, bot, onRun }: Props) {
  const [text, setText] = useState("");
  const [sentKey, setSentKey] = useState(0);

  return (
    <>
      <div className="inc-head">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span className="label">{place.state}{place.river ? ` · ${place.river}` : ""}</span>
          <Gauge level={place.level} />
        </div>
        <h2>{place.name}</h2>
        <p className="mono">{fmt(place.lat, 3)}°N {fmt(place.lon, 3)}°E · scored {ist(new Date())} IST</p>
      </div>

      <section className="sec" aria-labelledby="why-h">
        <div className="label" id="why-h">Why this level <span className="tag">rules, not the LLM</span></div>
        <ul className="why">
          {place.rules.length ? place.rules.map((r, i) => (
            <li key={i} style={{ ["--c" as string]: LEVEL_COLOR[r.level] }}>
              <span>{r.text}<small>{r.why} · {r.source}</small></span>
            </li>
          )) : <li>No data reached us. The level is unknown, never assumed safe.</li>}
        </ul>
      </section>

      <section className="sec" aria-labelledby="plan-h">
        <div className="label" id="plan-h">
          Response plan
          <span className="tag">{running ? "running" : steps.comms ? "done" : "ready"}{retries ? ` · ${retries} reroute${retries > 1 ? "s" : ""}` : ""}</span>
        </div>
        <label className="sr-only" htmlFor="sos-text">SOS message</label>
        <textarea id="sos-text" className="sos" lang="hi" value={text} onChange={(e) => setText(e.target.value)}
          placeholder="SOS text, in any language. Example: पानी घर में घुस गया है, 4 लोग फँसे हैं" />
        <p className="hint">Runs for an SOS at this point. Telegram and SMS messages arrive here the same way.</p>
        <button className="cta" disabled={running} onClick={() => onRun(text)}>{running ? "Running…" : steps.comms ? "Run again" : "Run response plan"}</button>
        {error && <div className="err" role="alert">{error}</div>}

        <ol className="trace" style={{ marginTop: 16 }} aria-live="polite">
          {STEPS.map((s, i) => {
            const ev = steps[s];
            const status: StepStatus = ev?.status ?? "idle";
            return (
              <li key={s} className="step" data-s={status}>
                <span className="dot">{status === "ok" ? "✓" : status === "fix" ? "↻" : status === "fail" ? "!" : i + 1}</span>
                <div>
                  <b>{STEP_LABEL[s]}</b>
                  <AnimatePresence mode="wait" initial={false}>
                    <motion.div key={ev ? `${ev.status}:${ev.text}` : "idle"} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
                      {/* trace text is generated server-side from escaped values */}
                      <p dangerouslySetInnerHTML={{ __html: ev?.text ?? "Waiting" }} />
                      {ev?.sources.map((src) => (
                        <span key={src} className={`src${src.startsWith("!") ? " warn" : ""}`}>{src.replace(/^!/, "")}</span>
                      ))}
                    </motion.div>
                  </AnimatePresence>
                </div>
                <span className="t">{ev?.ms != null && ev.status !== "run" ? `${ev.ms} ms` : ""}</span>
              </li>
            );
          })}
        </ol>
      </section>

      <AnimatePresence initial={false}>
        {message && (
          <motion.section key="msg" className="sec" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <div className="label">Drafted alert · {message.local ? `${message.lang} + ` : ""}Hindi + English</div>
            <div className="msg">
              {message.local && <div className="hi" style={{ marginBottom: 8 }}>{message.local}</div>}
              <div className="hi" lang="hi">{message.hi}</div>
              <div className="en">{message.en}</div>
            </div>
            {origin && <BroadcastBox bot={bot} message={message} place={origin} radiusKm={ZONE_KM[message.level]} onSent={() => setSentKey((k) => k + 1)} />}
          </motion.section>
        )}
      </AnimatePresence>

      <HeardFunnel refreshKey={sentKey} />
    </>
  );
}
