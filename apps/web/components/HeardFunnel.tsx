"use client";

import { useEffect, useState } from "react";
import { animate, motion, useMotionValue, useTransform } from "motion/react";
import { fetchFunnel, type Funnel } from "@/lib/api";

function Count({ value, color }: { value: number; color?: string }) {
  const mv = useMotionValue(value);
  const shown = useTransform(() => Math.round(mv.get()));
  useEffect(() => {
    const c = animate(mv, value, { duration: 0.6, ease: "easeOut" });
    return () => c.stop();
  }, [mv, value]);
  return <motion.b style={color ? { color } : undefined}>{shown}</motion.b>;
}

/** Live counts for the latest zone alert, polled while the panel is open. */
export default function HeardFunnel({ refreshKey }: { refreshKey: number }) {
  const [f, setF] = useState<Funnel | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () => fetchFunnel().then((d) => alive && (setF(d), setError(false))).catch(() => alive && setError(true));
    load();
    const id = setInterval(load, 4000);
    return () => { alive = false; clearInterval(id); };
  }, [refreshKey]);

  const a = f?.alerted ?? 0;
  const pct = (n: number) => (a ? `${(n / a) * 100}%` : "0%");
  return (
    <section className="sec" aria-labelledby="heard-h">
      <div className="label" id="heard-h">
        Heard → safe
        <span className="tag">{f?.alert ? `alert #${f.alert.id} · ${f.alert.place}` : error ? "server unreachable" : "no alert sent yet"}</span>
      </div>
      <div className="funnel" aria-live="polite">
        <div><Count value={a} /><span>alerted</span></div>
        <div><Count value={f?.heard ?? 0} /><span>heard</span></div>
        <div><Count value={f?.safe ?? 0} color="var(--g)" /><span>safe</span></div>
        <div><Count value={f?.help ?? 0} color="var(--r)" /><span>need help</span></div>
      </div>
      {a > 0 && (
        <div className="bar" aria-hidden="true">
          <motion.i animate={{ width: pct(f!.safe) }} style={{ background: "var(--g)" }} />
          <motion.i animate={{ width: pct(f!.help) }} style={{ background: "var(--r)" }} />
          <motion.i animate={{ width: pct(f!.heard - f!.safe - f!.help) }} style={{ background: "var(--river)" }} />
        </div>
      )}
      {f?.failed ? <p className="hint">{f.failed} could not be reached on Telegram.</p> : null}
    </section>
  );
}
