import { LineChart, Line, ResponsiveContainer, YAxis } from "recharts";
import { useCoordinationStore } from "@/stores/coordinationStore";

// A compact, axis-light sparkline — the full labeled time-series lives in
// the Experiment dashboard (§27). This is a live "is it stable right now"
// glance, not an analysis tool.
export default function LatencyPanel() {
  const history = useCoordinationStore((s) => s.history);

  return (
    <div style={{ display: "flex", gap: 16, height: 48 }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 9, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Tracking error
        </div>
        <ResponsiveContainer width="100%" height={32}>
          <LineChart data={history}>
            <YAxis hide domain={[0, "auto"]} />
            <Line type="monotone" dataKey="trackingError" stroke="var(--warn)" dot={false} strokeWidth={1.5} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 9, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Latency (ms)
        </div>
        <ResponsiveContainer width="100%" height={32}>
          <LineChart data={history}>
            <YAxis hide domain={[0, "auto"]} />
            <Line type="monotone" dataKey="latency" stroke="var(--accent)" dot={false} strokeWidth={1.5} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
