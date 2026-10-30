import type { Level } from "./types";

export const LEVEL_COLOR: Record<Level, string> = {
  green: "#22C55E",
  yellow: "#FACC15",
  orange: "#FB923C",
  red: "#EF4444",
  unknown: "#64748B",
};

export const LEVEL_HI: Record<Level, string> = {
  red: "लाल चेतावनी",
  orange: "नारंगी चेतावनी",
  yellow: "पीली चेतावनी",
  green: "कोई चेतावनी नहीं",
  unknown: "स्थिति अज्ञात",
};

export const fmt = (v: number | null | undefined, d = 0) => (v == null || Number.isNaN(v) ? "–" : v.toFixed(d));

export const ist = (d: Date) =>
  d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata" });
