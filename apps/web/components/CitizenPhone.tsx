"use client";

import { motion } from "motion/react";
import type { AlertMessage } from "@/lib/types";
import { LEVEL_COLOR, LEVEL_HI } from "@/lib/format";

export default function CitizenPhone({ message, placeName, driver, onToast }: {
  message: AlertMessage | null;
  placeName: string;
  driver: string | null;
  onToast: (t: string) => void;
}) {
  const speak = () => {
    if (!message) return;
    try {
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(message.hi);
      u.lang = "hi-IN";
      speechSynthesis.speak(u);
    } catch {
      onToast("Speech isn't available in this browser");
    }
  };

  return (
    <motion.div className="phone" aria-label="Citizen app preview"
      initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 24 }}
      transition={{ type: "spring", bounce: 0, visualDuration: 0.3 }}>
      <div className="notch" />
      {!message ? (
        <p className="empty">Run a response plan to see what the citizen receives.</p>
      ) : (
        <>
          <div className="alert" data-l={message.level} style={{ ["--lc" as string]: LEVEL_COLOR[message.level] }}>
            <small>{placeName} · {new Date().toLocaleDateString("hi-IN", { day: "numeric", month: "long" })}</small>
            <h4 lang="hi">{LEVEL_HI[message.level]}</h4>
            {driver && <p>{driver}</p>}
          </div>
          <ol className="todo" lang="hi">
            {message.steps_hi.map((s, i) => <li key={i}><span>{i + 1}</span>{s}</li>)}
          </ol>
          <button className="listen" lang="hi" onClick={speak}>सुनें · Listen</button>
          <div className="two">
            <motion.button whileTap={{ scale: 0.96 }} style={{ background: "#15803D" }} onClick={() => onToast("Safe reply recorded once the Telegram bot is connected")}>मैं सुरक्षित हूँ</motion.button>
            <motion.button whileTap={{ scale: 0.96 }} style={{ background: "#DC2626" }} onClick={() => onToast("Help request goes to dispatch once the Telegram bot is connected")}>मदद चाहिए</motion.button>
          </div>
        </>
      )}
    </motion.div>
  );
}
