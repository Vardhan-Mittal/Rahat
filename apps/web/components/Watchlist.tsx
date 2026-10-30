"use client";

import { motion } from "motion/react";
import type { Place } from "@/lib/types";
import { LEVEL_COLOR, fmt } from "@/lib/format";
import Gauge from "./Gauge";

function Spark({ values, color }: { values: number[] | null; color: string }) {
  if (!values?.length) return null;
  const v = values.map((x) => x || 0);
  const mx = Math.max(1, ...v);
  const w = 280, h = 26;
  const pts = v.map((y, i) => [(i / (v.length - 1)) * w, h - 2 - (y / mx) * (h - 6)]);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true">
      <path d={`${d} L${w} ${h} L0 ${h}Z`} fill={color} opacity={0.14} />
      <path d={d} fill="none" stroke={color} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
      <circle cx={pts[0][0]} cy={pts[0][1]} r={2.5} fill={color} />
    </svg>
  );
}

export default function Watchlist({ places, selected, onSelect }: { places: Place[]; selected: string | null; onSelect: (id: string) => void }) {
  return (
    <>
      {places.map((p) => {
        const reason = p.driver && p.driver.level !== "green" ? p.driver.text.split(":")[0].split(",")[0] : null;
        return (
          // layout: cards glide to their new rank when levels change on refresh
          <motion.button layout="position" transition={{ type: "spring", bounce: 0, visualDuration: 0.35 }}
            key={p.id} className="place" aria-current={selected === p.id} onClick={() => onSelect(p.id)}>
            <h3>{p.name}</h3>
            <Gauge level={p.level} />
            <span className="sub">{p.state}{reason ? ` · ${reason}` : ""}</span>
            <span className="metrics">
              <span>Rain 24h <b>{fmt(p.rain24)}</b> mm</span>
              <span>River <b>{p.ratio ? `${fmt(p.ratio, 1)}×` : "–"}</b></span>
              <span>Max <b>{fmt(p.tmax)}</b>°</span>
            </span>
            <Spark values={p.rain7} color={LEVEL_COLOR[p.level]} />
          </motion.button>
        );
      })}
    </>
  );
}
