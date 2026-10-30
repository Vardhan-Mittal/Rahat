import type { Level } from "@/lib/types";

export default function Gauge({ level }: { level: Level }) {
  return (
    <span className="gauge" data-l={level}>
      <span className="seg" aria-hidden="true"><i /><i /><i /><i /></span>
      {level === "unknown" ? "NO DATA" : level.toUpperCase()}
    </span>
  );
}
