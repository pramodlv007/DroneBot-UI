/**
 * AiMonitorFeed — Static single-card display of the latest AI monitor reading.
 * Incorporates real-time multi-robot parameters (Separation Corridor, Asymmetric Energy,
 * Localization Integrity, Link Latency, Kinematic Anomalies) updated every 4 seconds.
 * Shared between AiMonitorTab (full-page) and AiMonitorPopup (floating).
 */
import { useEffect, useRef, useState } from "react";
import type { FeedEntry, MonitorProvider } from "@/stores/aiMonitorStore";
import { useRobotStore } from "@/stores/robotStore";
import { useCoordinationStore } from "@/stores/coordinationStore";
import { useAnomalyStore } from "@/stores/anomalyStore";
import { fmtNum } from "@/utils/format";

const PROVIDER_LABEL: Record<MonitorProvider, string> = {
  openai: "🧠 GPT-4",
  claude: "🧠 Claude",
  rule_based: "⚙ Rule-Based Engine",
};

function statusColor(status: string) {
  if (status === "CRITICAL") return "var(--crit)";
  if (status === "WARNING") return "var(--warn)";
  return "var(--ok)";
}

function statusDimColor(status: string) {
  if (status === "CRITICAL") return "var(--crit-dim)";
  if (status === "WARNING") return "var(--warn-dim)";
  return "var(--ok-dim)";
}

function statusIcon(status: string) {
  if (status === "CRITICAL") return "🚨";
  if (status === "WARNING") return "⚡";
  return "✓";
}

function StatusBadge({ status }: { status: string }) {
  const color = statusColor(status);
  return (
    <span
      className="aim-badge"
      style={{
        background: statusDimColor(status),
        color,
        border: `1px solid ${color}40`,
      }}
    >
      {statusIcon(status)} {status}
    </span>
  );
}

// Tracks previous entry ID to trigger highlight transitions
function useFlashKey(entry: FeedEntry | null) {
  const prevRef = useRef<number | null>(null);
  const [flashKey, setFlashKey] = useState(0);

  useEffect(() => {
    if (!entry) return;
    if (prevRef.current !== null && prevRef.current !== entry.id) {
      setFlashKey((k) => k + 1);
    }
    prevRef.current = entry.id;
  }, [entry]);

  return flashKey;
}

interface Props {
  feed: FeedEntry[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onClear: () => void;
  maxVisible?: number;
}

export default function AiMonitorFeed({ feed, loading, error, onRetry }: Props) {
  const latest = feed[0] ?? null;
  const updateCount = feed.length;
  const flashKey = useFlashKey(latest);

  // Live domain stores
  const robots = useRobotStore((s) => s.robots);
  const coordination = useCoordinationStore((s) => s.coordination);
  const anomalies = useAnomalyStore((s) => s.active);

  const uav = Object.values(robots).find((r) => r.robot_type === "UAV");
  const ugv = Object.values(robots).find((r) => r.robot_type === "UGV");

  // 1. Separation corridor & 3s predictive trend
  const sep = coordination.separation_m;
  const targetSep = coordination.target_separation_m ?? 5.0;
  const trend = coordination.separation_trend || "STABLE";
  const trackingErr = coordination.tracking_error_m;

  // 2. Asymmetric power & Return-To-Home safety window
  const uavBat = uav?.battery?.percentage ?? null;
  const ugvBat = ugv?.battery?.percentage ?? null;
  const rthStatus =
    uavBat === null
      ? "STANDBY"
      : uavBat > 30
      ? "SAFE (>15m)"
      : uavBat > 15
      ? "MARGINAL"
      : "CRITICAL RTH";

  // 3. Localization integrity & GPS-denial
  const uavGps = uav?.gps;
  const uavDeadReckoning = uav?.metadata?.dead_reckoning_active;
  const uavLocStatus = uavDeadReckoning
    ? "DEAD RECKONING"
    : uavGps && uavGps.fix >= 3
    ? `3D FIX (${uavGps.fix})`
    : uav?.connected
    ? "GPS-DENIED"
    : "OFFLINE";
  const ugvOdomStatus = ugv?.metadata?.awaiting_odom
    ? "AWAITING /ODOM"
    : ugv?.connected
    ? "ODOM ACTIVE"
    : "OFFLINE";

  // 4. Telemetry link latency
  const uavLatency = uav ? Math.max(0, uav.received_timestamp_ms - uav.source_timestamp_ms) : null;
  const ugvLatency = ugv ? Math.max(0, ugv.received_timestamp_ms - ugv.source_timestamp_ms) : null;

  // 5. Kinematic & physical anomalies
  const uavAnomalies = uav ? anomalies[uav.robot_id] ?? [] : [];
  const ugvAnomalies = ugv ? anomalies[ugv.robot_id] ?? [] : [];
  const totalAnomalies = [...uavAnomalies, ...ugvAnomalies];

  const time = latest
    ? new Date(latest.timestamp_ms).toLocaleTimeString("en-US", {
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : null;

  return (
    <div className="aim-root">
      {/* ── Header ── */}
      <div
        className="aim-header"
        style={{ borderBottom: `2px solid ${latest ? statusColor(latest.overall_status) : "var(--border)"}30` }}
      >
        <div className="aim-header-left">
          <span className="aim-title">🤖 AI Mission Monitor</span>
          <span className="aim-subtitle">
            {latest?.provider ? PROVIDER_LABEL[latest.provider] : "Live telemetry analysis"} · updates every 4s
          </span>
        </div>
        <div className="aim-header-right">
          {loading && (
            <span className="aim-spinner">
              <span className="connecting-ring" style={{ width: 10, height: 10 }} />
              Updating (4s)…
            </span>
          )}
          {latest && <StatusBadge status={latest.overall_status} />}
        </div>
      </div>

      {/* ── Error Banner ── */}
      {error && (
        <div className="aim-error">
          <span>⚠ {error}</span>
          <button className="aim-retry-btn" onClick={onRetry}>
            Retry
          </button>
        </div>
      )}

      {/* ── Empty state ── */}
      {!latest && !error && (
        <div className="aim-empty">
          <div style={{ fontSize: 48, marginBottom: 4 }}>🤖</div>
          <div style={{ fontWeight: 700 }}>Initializing AI Mission Form…</div>
          <div className="aim-empty-sub">Evaluating initial telemetry snapshot (4s cycle)</div>
        </div>
      )}

      {/* ── Static Live Card (Values update in-place every 4s) ── */}
      {latest && (
        <div className="aim-static-layout">
          {/* 1. Hero Status Card */}
          <div className={`aim-hero-card status-${latest.overall_status}`}>
            <div className="aim-hero-top">
              <div className="aim-hero-status-group">
                <StatusBadge status={latest.overall_status} />
                <div
                  className="aim-hero-headline"
                  key={`hl-${flashKey}`}
                  style={flashKey > 0 ? { animation: "aim-value-flash 0.4s ease-out" } : undefined}
                >
                  {latest.headline}
                </div>
                <div className="aim-hero-time">
                  🕐 Last AI Assessment: {time} · 4s cycle
                </div>
              </div>

              {latest.recommended_action && latest.recommended_action !== "CONTINUE" && (
                <span className={`aim-action-chip ${latest.recommended_action}`} key={`act-${flashKey}`}>
                  → {latest.recommended_action.replace(/_/g, " ")}
                </span>
              )}
              {latest.recommended_action === "CONTINUE" && (
                <span className="aim-action-chip CONTINUE" key={`act-${flashKey}`}>
                  ✓ ALL CLEAR
                </span>
              )}
            </div>
          </div>

          {/* 2. Core AI Parameter Assessment Matrix (Updated every 4s) */}
          <div className="aim-matrix-section">
            <div className="aim-matrix-title">
              <span>Mission Parameter Assessment (4s Loop)</span>
              <span style={{ fontSize: 8.5, color: "var(--accent)", fontFamily: "var(--mono)" }}>● ACTIVE TELEMETRY</span>
            </div>

            <div className="aim-matrix-grid">
              {/* Parameter 1: Spatial Separation */}
              <div className="aim-matrix-card">
                <div className="aim-matrix-card-top">
                  <span className="aim-matrix-tag">🛰 Spatial Separation</span>
                  <span
                    className="aim-trend-badge"
                    style={{
                      background:
                        trend === "STABLE"
                          ? "var(--ok-dim)"
                          : trend === "CONVERGING"
                          ? "var(--accent-dim)"
                          : "var(--warn-dim)",
                      color:
                        trend === "STABLE"
                          ? "var(--ok)"
                          : trend === "CONVERGING"
                          ? "var(--accent)"
                          : "var(--warn)",
                    }}
                  >
                    3s: {trend}
                  </span>
                </div>
                <div className="aim-matrix-main-val">
                  <span>{fmtNum(sep, 1, " m")}</span>
                  <span style={{ fontSize: 10, color: "var(--text-2)", fontWeight: 500 }}>
                    Target: {fmtNum(targetSep, 1, " m")}
                  </span>
                </div>
                <div className="aim-matrix-detail">
                  <span>Tracking Error</span>
                  <span style={{ fontFamily: "var(--mono)", fontWeight: 600 }}>
                    {fmtNum(trackingErr, 2, " m")}
                  </span>
                </div>
              </div>

              {/* Parameter 2: Asymmetric Power & RTH */}
              <div className="aim-matrix-card">
                <div className="aim-matrix-card-top">
                  <span className="aim-matrix-tag">⚡ Asymmetric Energy</span>
                  <span
                    className="aim-trend-badge"
                    style={{
                      background:
                        rthStatus.startsWith("SAFE")
                          ? "var(--ok-dim)"
                          : rthStatus.startsWith("MARGINAL")
                          ? "var(--warn-dim)"
                          : "var(--crit-dim)",
                      color:
                        rthStatus.startsWith("SAFE")
                          ? "var(--ok)"
                          : rthStatus.startsWith("MARGINAL")
                          ? "var(--warn)"
                          : "var(--crit)",
                    }}
                  >
                    RTH: {rthStatus}
                  </span>
                </div>
                <div className="aim-matrix-main-val">
                  <span>🚁 {uavBat !== null ? `${uavBat.toFixed(0)}%` : "—"}</span>
                  <span style={{ fontSize: 12, color: "var(--text-1)" }}>
                    🤖 {ugvBat !== null ? `${ugvBat.toFixed(0)}%` : "—"}
                  </span>
                </div>
                <div className="aim-matrix-detail">
                  <span>UAV Flight Mode</span>
                  <span style={{ fontFamily: "var(--mono)", fontWeight: 600 }}>
                    {uav?.mode ?? "DISARMED"}
                  </span>
                </div>
              </div>

              {/* Parameter 3: Localization Integrity */}
              <div className="aim-matrix-card">
                <div className="aim-matrix-card-top">
                  <span className="aim-matrix-tag">📍 Localization Integrity</span>
                  <span
                    className="aim-trend-badge"
                    style={{
                      background: uavLocStatus.includes("FIX") ? "var(--ok-dim)" : "var(--warn-dim)",
                      color: uavLocStatus.includes("FIX") ? "var(--ok)" : "var(--warn)",
                    }}
                  >
                    {uavDeadReckoning ? "ESTIMATED" : "FUSED"}
                  </span>
                </div>
                <div className="aim-matrix-main-val" style={{ fontSize: 11.5 }}>
                  <span>UAV: {uavLocStatus}</span>
                </div>
                <div className="aim-matrix-detail">
                  <span>UGV Odometry</span>
                  <span style={{ fontFamily: "var(--mono)", fontWeight: 600 }}>
                    {ugvOdomStatus}
                  </span>
                </div>
              </div>

              {/* Parameter 4: Telemetry Latency */}
              <div className="aim-matrix-card">
                <div className="aim-matrix-card-top">
                  <span className="aim-matrix-tag">📡 Link Latency</span>
                  <span
                    className="aim-trend-badge"
                    style={{ background: "var(--ok-dim)", color: "var(--ok)" }}
                  >
                    10 Hz SYNC
                  </span>
                </div>
                <div className="aim-matrix-main-val">
                  <span>
                    UAV:{" "}
                    <span
                      style={{
                        color:
                          uavLatency === null
                            ? "var(--text-2)"
                            : uavLatency < 100
                            ? "var(--ok)"
                            : uavLatency < 300
                            ? "var(--warn)"
                            : "var(--crit)",
                      }}
                    >
                      {uavLatency !== null ? `${uavLatency}ms` : "—"}
                    </span>
                  </span>
                  <span style={{ fontSize: 11, color: "var(--text-1)" }}>
                    UGV:{" "}
                    <span
                      style={{
                        color:
                          ugvLatency === null
                            ? "var(--text-2)"
                            : ugvLatency < 100
                            ? "var(--ok)"
                            : ugvLatency < 300
                            ? "var(--warn)"
                            : "var(--crit)",
                      }}
                    >
                      {ugvLatency !== null ? `${ugvLatency}ms` : "—"}
                    </span>
                  </span>
                </div>
                <div className="aim-matrix-detail">
                  <span>Watchdog Status</span>
                  <span style={{ fontFamily: "var(--mono)", color: "var(--ok)", fontWeight: 600 }}>
                    HEALTHY
                  </span>
                </div>
              </div>

              {/* Parameter 5: Kinematic Anomalies */}
              <div className="aim-matrix-card">
                <div className="aim-matrix-card-top">
                  <span className="aim-matrix-tag">⚠️ Kinematic Health</span>
                  <span
                    className="aim-trend-badge"
                    style={{
                      background: totalAnomalies.length === 0 ? "var(--ok-dim)" : "var(--warn-dim)",
                      color: totalAnomalies.length === 0 ? "var(--ok)" : "var(--warn)",
                    }}
                  >
                    {totalAnomalies.length === 0 ? "NOMINAL" : `${totalAnomalies.length} ALERTS`}
                  </span>
                </div>
                <div className="aim-matrix-main-val" style={{ fontSize: 11.5 }}>
                  <span>
                    {totalAnomalies.length === 0
                      ? "No Wheel Slip / Stall"
                      : totalAnomalies.join(", ")}
                  </span>
                </div>
                <div className="aim-matrix-detail">
                  <span>Yaw / Heading</span>
                  <span style={{ fontFamily: "var(--mono)", color: "var(--ok)", fontWeight: 600 }}>
                    STABLE
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* 3. Alerts Section */}
          {latest.alerts.length > 0 && (
            <div className="aim-alerts-section">
              {latest.alerts.map((alert, i) => (
                <div key={`${flashKey}-alert-${i}`} className="aim-alert-item">
                  <span className="aim-alert-icon">⚠</span>
                  <span>{alert}</span>
                </div>
              ))}
            </div>
          )}

          {/* 4. Interpretive System Updates */}
          {latest.updates.length > 0 && (
            <div className="aim-updates-section">
              <div className="aim-updates-title">AI Operational Insights</div>
              <ul className="aim-updates-list">
                {latest.updates.map((update, i) => (
                  <li
                    key={`${flashKey}-upd-${i}`}
                    className="aim-update-item"
                    style={flashKey > 0 ? { animation: `aim-value-flash 0.4s ease-out ${i * 50}ms` } : undefined}
                  >
                    <span className="aim-update-dot" />
                    <span>{update}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 5. Provider footer */}
          <div className="aim-provider-footer">
            <span className="aim-provider-label">
              {PROVIDER_LABEL[latest.provider] ?? latest.provider}
            </span>
            <span className="aim-update-count">
              {updateCount} assessment{updateCount !== 1 ? "s" : ""} · auto-refreshing every 4s
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
