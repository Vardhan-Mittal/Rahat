"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import QRCode from "qrcode";
import type { BotInfo } from "@/lib/api";

/** QR code so judges and the audience can join the alert bot during the demo. */
export default function JoinAlerts({ bot }: { bot: BotInfo | null }) {
  const [open, setOpen] = useState(false);
  const [qr, setQr] = useState<string | null>(null);

  useEffect(() => {
    if (bot?.link) QRCode.toDataURL(`${bot.link}?start=join`, { margin: 1, width: 220, color: { dark: "#0B1220", light: "#F5F6F8" } }).then(setQr);
  }, [bot?.link]);

  if (!bot?.enabled) return null;
  return (
    <div style={{ position: "relative" }}>
      <button className="toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>Join alerts</button>
      <AnimatePresence>
        {open && (
          <motion.div key="qr" className="qr" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.18 }}>
            {/* eslint-disable-next-line @next/next/no-img-element -- generated data URL, nothing to optimise */}
            {qr && <img src={qr} alt={`QR code for ${bot.link}`} width={220} height={220} />}
            <p>Scan, press Start, then share your location to get alerts for your area.</p>
            <a href={bot.link!} target="_blank" rel="noreferrer" className="mono">t.me/{bot.username}</a>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
