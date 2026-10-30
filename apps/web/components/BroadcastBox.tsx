"use client";

import { useEffect, useState } from "react";
import { fetchRecipients, sendBroadcast, type BotInfo } from "@/lib/api";
import type { AlertMessage } from "@/lib/types";

type Props = {
  bot: BotInfo | null;
  message: AlertMessage;
  place: { name: string; lat: number; lon: number };
  radiusKm: number;
  onSent: () => void;
};

/** Two-step operator approval: see who is in the zone, then confirm the send. */
export default function BroadcastBox({ bot, message, place, radiusKm, onSent }: Props) {
  const [count, setCount] = useState<number | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The parent remounts this box (via key) for each new alert, so local state starts fresh.
  useEffect(() => {
    fetchRecipients(place.lat, place.lon, radiusKm).then((d) => setCount(d.count)).catch(() => setCount(null));
  }, [place.lat, place.lon, radiusKm]);

  if (!bot?.enabled) {
    return <p className="hint">Zone alerts go out on Telegram. Add a bot token on the server to turn them on.</p>;
  }

  const send = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await sendBroadcast({
        place: place.name, level: message.level, lat: place.lat, lon: place.lon, radius_km: radiusKm,
        hi: message.hi, en: message.en, local: message.local, lang: message.lang, shelter: message.shelter,
      });
      setResult(`Sent to ${r.sent} of ${r.recipients} people. Replies appear below as they come in.`);
      onSent();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sending failed");
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  };

  return (
    <div style={{ marginTop: 12 }}>
      <p className="hint" style={{ marginTop: 0 }}>
        {count == null ? "Counting opted-in people in the zone…" : `${count} ${count === 1 ? "person has" : "people have"} opted in within ${radiusKm} km of this point.`}
      </p>
      {!confirming ? (
        <button className="cta" style={{ background: "transparent", color: "var(--ink)", border: "1px solid var(--line-2)" }}
          onClick={() => (count ? setConfirming(true) : setError("Nobody in this zone has opted in yet. Share the join link first."))}>
          Send this alert to the zone
        </button>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <button className="cta" style={{ background: "transparent", color: "var(--ink)", border: "1px solid var(--line-2)" }} onClick={() => setConfirming(false)}>Cancel</button>
          <button className="cta" style={{ background: "var(--r)", color: "#fff" }} disabled={busy} onClick={send}>
            {busy ? "Sending…" : `Approve and send to ${count}`}
          </button>
        </div>
      )}
      {result && <p className="hint" role="status">{result}</p>}
      {error && <div className="err" role="alert">{error}</div>}
    </div>
  );
}
