/**
 * MissionHealthGauge — circular SVG gauge showing the backend-computed
 * mission health score (0–100). Every data point comes from real backend
 * computation: tracking accuracy, latency, battery, GPS quality, and
 * safety event counts — all weighted and composited in
 * coordination_manager.compute_mission_health_score().
 *
 * Hover shows the per-factor breakdown tooltip.
 */
import { useState } from "react";
import { useCoordinationStore } from "@/stores/coordinationStore";
import type { MissionHealthComponents } from "@/types/coordination";
import { fmtNum } from "@/utils/format";

function scoreColor(score: number | null): string {
  if (score == null) return "var(--text-2)";
  if (score >= 70) return "var(--ok)";
  if (score >= 40) return "var(--warn)";
  return "var(--crit)";
}

function scoreLabel(score: number | null): string {
  if (score == null) return "—";
  if (score >= 80) return "EXCELLENT";
  if (score >= 60) return "GOOD";
  if (score >= 40) return "FAIR";
  if (score >= 20) return "POOR";
  return "CRITICAL";
}

const FACTOR_LABELS: Record<keyof MissionHealthComponents, { label: string; icon: string }> = {
  tracking: { label: "Tracking", icon: "🎯" },
  latency: { label: "Latency", icon: "📡" },
  battery: { label: "Battery", icon: "🔋" },
  gps: { label: "GPS", icon: "🛰️" },
  safety: { label: "Safety", icon: "🛡️" },
};

export default function MissionHealthGauge() {
  const coord = useCoordinationStore((s) => s.coordination);
  const [hovered, setHovered] = useState(false);

  const score = coord.mission_health_score;
  const components = coord.mission_health_components;
  const color = scoreColor(score);

  // SVG arc parameters
  const size = 48;
  const strokeWidth = 4;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = score != null ? Math.max(0, Math.min(100, score)) / 100 : 0;
  const dashOffset = circumference * (1 - progress);

  return (
    <div
      className="health-gauge-wrap"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <svg width={size} height={size} className="health-gauge-svg">
        {/* Background track */}
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none"
          stroke="rgba(30,42,61,0.6)"
          strokeWidth={strokeWidth}
        />
        {/* Score arc */}
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          transform={`rotate(-90, ${size / 2}, ${size / 2})`}
          style={{ transition: "stroke-dashoffset 0.5s ease, stroke 0.3s ease" }}
        />
        {/* Center score text */}
        <text
          x={size / 2} y={size / 2 + 1}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={score != null ? 12 : 9}
          fontWeight="bold"
          fill={color}
          style={{ fontFamily: "var(--mono)" }}
        >
          {score != null ? Math.round(score) : "—"}
        </text>
      </svg>

      <div className="health-gauge-label">
        <span style={{ fontSize: 8.5, color: "var(--text-2)", textTransform: "uppercase", fontWeight: 700 }}>
          HEALTH
        </span>
        <span style={{ fontSize: 9, color, fontWeight: 600, fontFamily: "var(--mono)" }}>
          {scoreLabel(score)}
        </span>
      </div>

      {/* Hover breakdown tooltip */}
      {hovered && components && (
        <div className="health-gauge-tooltip">
          <div className="health-gauge-tooltip-title">Mission Health Breakdown</div>
          {Object.entries(FACTOR_LABELS).map(([key, { label, icon }]) => {
            const val = components[key as keyof MissionHealthComponents] ?? 0;
            const factorColor = val >= 70 ? "var(--ok)" : val >= 40 ? "var(--warn)" : "var(--crit)";
            return (
              <div key={key} className="health-gauge-factor">
                <span className="health-gauge-factor-icon">{icon}</span>
                <span className="health-gauge-factor-label">{label}</span>
                <div className="health-gauge-factor-bar">
                  <div
                    className="health-gauge-factor-fill"
                    style={{ width: `${val}%`, background: factorColor }}
                  />
                </div>
                <span className="health-gauge-factor-val" style={{ color: factorColor }}>
                  {fmtNum(val, 0)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
