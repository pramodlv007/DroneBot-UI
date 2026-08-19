import { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { api } from "@/services/api";
import type { ExperimentDetail, ExperimentSummary } from "@/types/experiment";
import { fmtDuration, fmtNum, fmtTime } from "@/utils/format";

interface ChartPoint {
  t: number;
  trackingError: number | null;
  separation: number | null;
  latency: number | null;
  headingError: number | null;
}

export default function ExperimentPanel() {
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [compareId, setCompareId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ExperimentDetail | null>(null);
  const [series, setSeries] = useState<ChartPoint[]>([]);
  const [compareSeries, setCompareSeries] = useState<ChartPoint[]>([]);

  useEffect(() => {
    api.listExperiments().then(setExperiments).catch(() => setExperiments([]));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    api.getExperiment(selectedId).then(setDetail);
    loadSeries(selectedId).then(setSeries);
  }, [selectedId]);

  useEffect(() => {
    if (!compareId) {
      setCompareSeries([]);
      return;
    }
    loadSeries(compareId).then(setCompareSeries);
  }, [compareId]);

  async function loadSeries(id: string): Promise<ChartPoint[]> {
    const rows = await api.getExperimentCoordination(id);
    const start = rows[0]?.timestamp_ms ?? 0;
    return rows.map((r) => {
      const s = JSON.parse(r.state_json);
      return {
        t: (r.timestamp_ms - start) / 1000,
        trackingError: s.tracking_error_m,
        separation: s.separation_m,
        latency: s.telemetry_latency_ms,
        headingError: s.heading_error_deg,
      };
    });
  }

  const metrics = detail?.metrics;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 16, height: "100%" }}>
      <div className="panel" style={{ overflowY: "auto" }}>
        <div className="panel-title">Experiments</div>
        {experiments.length === 0 && <div className="empty-state">No recorded experiments yet</div>}
        {experiments.map((exp) => (
          <div
            key={exp.id}
            onClick={() => setSelectedId(exp.id)}
            style={{
              padding: "8px 10px",
              borderRadius: 6,
              cursor: "pointer",
              marginBottom: 4,
              background: selectedId === exp.id ? "var(--bg-3)" : "transparent",
              border: `1px solid ${selectedId === exp.id ? "var(--accent)" : "transparent"}`,
            }}
          >
            <div style={{ fontWeight: 600, fontSize: 12 }}>{exp.name ?? exp.id}</div>
            <div style={{ fontSize: 10.5, color: "var(--text-2)" }}>
              {fmtTime(exp.started_at_ms)} · {exp.status}
            </div>
            <button
              style={{ marginTop: 4, fontSize: 9.5, padding: "2px 6px" }}
              onClick={(e) => {
                e.stopPropagation();
                setCompareId(compareId === exp.id ? null : exp.id);
              }}
            >
              {compareId === exp.id ? "✓ comparing" : "compare"}
            </button>
          </div>
        ))}
      </div>

      <div className="page-content" style={{ padding: 0 }}>
        {!detail ? (
          <div className="empty-state">Select an experiment to view its metrics and charts.</div>
        ) : (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <div>
                <h2 style={{ margin: 0 }}>{detail.experiment.name ?? detail.experiment.id}</h2>
                <div style={{ color: "var(--text-2)", fontSize: 11 }}>
                  {detail.experiment.leader_id} → {detail.experiment.follower_id} · {detail.experiment.git_commit ?? "no commit"} ·{" "}
                  {detail.experiment.llm_provider}
                </div>
              </div>
              <div>
                <a href={api.exportExperimentUrl(detail.experiment.id, "json")} target="_blank" rel="noreferrer">
                  <button>Export JSON</button>
                </a>{" "}
                <a href={api.exportExperimentUrl(detail.experiment.id, "csv")} target="_blank" rel="noreferrer">
                  <button>Export CSV</button>
                </a>
              </div>
            </div>

            <div className="metric-grid">
              <Metric label="Tracking RMSE" value={fmtNum(metrics?.tracking_rmse_m, 2, " m")} />
              <Metric label="Mean tracking error" value={fmtNum(metrics?.mean_tracking_error_m, 2, " m")} />
              <Metric label="Max tracking error" value={fmtNum(metrics?.max_tracking_error_m, 2, " m")} />
              <Metric label="P95 tracking error" value={fmtNum(metrics?.p95_tracking_error_m, 2, " m")} />
              <Metric label="Mean separation" value={fmtNum(metrics?.mean_separation_m, 2, " m")} />
              <Metric label="Mean latency" value={fmtNum(metrics?.mean_latency_ms, 0, " ms")} />
              <Metric label="Duration" value={fmtDuration(metrics?.mission_duration_s)} />
              <Metric label="Role switches" value={String(metrics?.role_switch_count ?? 0)} />
              <Metric label="Warnings" value={String(metrics?.warning_count ?? 0)} />
              <Metric label="Critical events" value={String(metrics?.critical_event_count ?? 0)} />
              <Metric label="LLM recommendations" value={String(metrics?.llm_recommendation_count ?? 0)} />
              <Metric label="Mean LLM latency" value={fmtNum(metrics?.mean_llm_latency_ms, 0, " ms")} />
            </div>

            <ChartBox title="Tracking error vs time (s)" dataKey="trackingError" unit="m" series={series} compareSeries={compareSeries} />
            <ChartBox title="Separation vs time (s)" dataKey="separation" unit="m" series={series} compareSeries={compareSeries} />
            <ChartBox title="Latency vs time (s)" dataKey="latency" unit="ms" series={series} compareSeries={compareSeries} />
            <ChartBox title="Heading error vs time (s)" dataKey="headingError" unit="deg" series={series} compareSeries={compareSeries} />
          </>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-tile">
      <div className="metric-label">{label}</div>
      <div className="metric-value mono">{value}</div>
    </div>
  );
}

function ChartBox({
  title,
  dataKey,
  unit,
  series,
  compareSeries,
}: {
  title: string;
  dataKey: keyof ChartPoint;
  unit: string;
  series: ChartPoint[];
  compareSeries: ChartPoint[];
}) {
  return (
    <div className="chart-box">
      <h3>
        {title} ({unit})
      </h3>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={series}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--bg-3)" />
          <XAxis dataKey="t" type="number" stroke="var(--text-2)" fontSize={10} label={{ value: "s", position: "insideBottomRight", offset: -2, fill: "var(--text-2)" }} />
          <YAxis stroke="var(--text-2)" fontSize={10} />
          <Tooltip contentStyle={{ background: "var(--bg-2)", border: "1px solid var(--border)", fontSize: 11 }} />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          <Line type="monotone" dataKey={dataKey} name="selected" stroke="var(--accent)" dot={false} strokeWidth={1.5} isAnimationActive={false} />
          {compareSeries.length > 0 && (
            <Line data={compareSeries} type="monotone" dataKey={dataKey} name="compare" stroke="var(--warn)" dot={false} strokeWidth={1.5} isAnimationActive={false} />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
