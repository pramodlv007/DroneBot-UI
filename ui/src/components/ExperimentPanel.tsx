import { useCallback, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { api } from "@/services/api";
import { Link } from "react-router-dom";
import { useAsyncData } from "@/hooks/useAsyncData";
import LoadState from "./LoadState";
import { fmtDuration, fmtNum, fmtTime } from "@/utils/format";

interface ChartPoint {
  t: number;
  trackingError: number | null;
  separation: number | null;
  latency: number | null;
  headingError: number | null;
}

export default function ExperimentPanel() {
  const list = useAsyncData(api.listExperiments);
  const experiments = list.data ?? [];
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [compareId, setCompareId] = useState<string | null>(null);
  const loadDetail = useCallback(async () => {
    const [detail, series] = await Promise.all([api.getExperiment(selectedId!), loadSeries(selectedId!)]);
    return { detail, series };
  }, [selectedId]);
  const loadComparison = useCallback(() => loadSeries(compareId!), [compareId]);
  const selected = useAsyncData(selectedId ? loadDetail : null);
  const comparison = useAsyncData(compareId ? loadComparison : null);
  const detail = selected.data?.detail;
  const series = selected.data?.series ?? [];
  const compareSeries = comparison.data ?? [];

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
    <div className="review-layout">
      <div className="panel review-sidebar">
        <div className="panel-title">Experiments</div>
        <LoadState {...list} />
        {!list.loading && !list.error && experiments.length === 0 && <div className="empty-state"><p>No recordings yet. Enable recording when starting a mission.</p><Link to="/?view=mission">Open mission control</Link></div>}
        {experiments.map((exp) => (
          <div
            key={exp.id}
            style={{
              padding: "8px 10px",
              borderRadius: 6,
              cursor: "pointer",
              marginBottom: 4,
              background: selectedId === exp.id ? "var(--bg-3)" : "transparent",
              border: `1px solid ${selectedId === exp.id ? "var(--accent)" : "transparent"}`,
            }}
          >
            <button className="recording-choice" aria-pressed={selectedId === exp.id} onClick={() => setSelectedId(exp.id)}>
              <strong>{exp.name ?? exp.id}</strong>
              <span>{fmtTime(exp.started_at_ms)} · {exp.status}</span>
            </button>
            <button
              style={{ marginTop: 4, fontSize: 9.5, padding: "2px 6px" }}
              aria-pressed={compareId === exp.id}
              aria-label={`Compare ${exp.name ?? exp.id}`}
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

      <div className="review-detail">
        <LoadState {...selected} />
        <LoadState {...comparison} />
        {selected.loading || selected.error ? null : !detail ? (
          <div className="empty-state">Select an experiment to view its metrics and charts.</div>
        ) : (
          <>
            <div className="page-heading">
              <div>
                <h2 style={{ margin: 0 }}>{detail.experiment.name ?? detail.experiment.id}</h2>
                <div style={{ color: "var(--text-2)", fontSize: 11 }}>
                  {detail.experiment.leader_id} → {detail.experiment.follower_id} · {detail.experiment.git_commit ?? "no commit"} ·{" "}
                  {detail.experiment.llm_provider}
                </div>
              </div>
              <div>
                <a className="button-link" href={api.exportExperimentUrl(detail.experiment.id, "json")} target="_blank" rel="noreferrer">Export JSON</a>{" "}
                <a className="button-link" href={api.exportExperimentUrl(detail.experiment.id, "csv")} target="_blank" rel="noreferrer">Export CSV</a>
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
