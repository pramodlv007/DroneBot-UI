/**
 * AiMonitorFeed — presentational rendering of the AI monitor feed, shared
 * between the full-page AiMonitorTab and the floating AiMonitorPopup so
 * there's exactly one implementation of "what a monitor update looks
 * like." Both consumers read from the same aiMonitorStore.
 */
import type { FeedEntry, MonitorProvider } from "@/stores/aiMonitorStore";

const PROVIDER_LABEL: Record<MonitorProvider, string> = {
  openai: "🧠 GPT",
  claude: "🧠 Claude",
  rule_based: "⚙ RULE-BASED (no AI key configured)",
};

const PROVIDER_COLOR: Record<MonitorProvider, string> = {
  openai: "var(--accent-bright)",
  claude: "var(--accent-bright)",
  rule_based: "var(--text-2)",
};

// Same vocabulary/colors as SupervisorPanel.tsx's ACTION_COLOR — one
// consistent action language regardless of which of the two AI systems
// (the always-on MissionSupervisor vs this on-demand monitor) produced it.
const ACTION_COLOR: Record<string, string> = {
  CONTINUE: "var(--ok)",
  SLOW_DOWN: "var(--warn)",
  PAUSE: "var(--warn)",
  STOP: "var(--crit)",
  CHECK_GPS: "var(--warn)",
  CHECK_COMMUNICATION: "var(--warn)",
  RETURN_TO_SAFE_STATE: "var(--crit)",
};

function statusColor(status: string) {
  if (status === "CRITICAL") return "var(--crit)";
  if (status === "WARNING") return "var(--warn)";
  return "var(--ok)";
}

function statusDimColor(status: string) {
  if (status === "CRITICAL") return "var(--crit-dim, rgba(255,80,80,0.10))";
  if (status === "WARNING") return "var(--warn-dim, rgba(255,180,58,0.10))";
  return "var(--ok-dim, rgba(60,215,120,0.10))";
}

function statusIcon(status: string) {
  if (status === "CRITICAL") return "🚨";
  if (status === "WARNING") return "⚡";
  return "✓";
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className="aim-badge"
      style={{
        background: statusDimColor(status),
        color: statusColor(status),
        border: `1px solid ${statusColor(status)}40`,
      }}
    >
      {statusIcon(status)} {status}
    </span>
  );
}

function AlertStrip({ alerts }: { alerts: string[] }) {
  if (!alerts.length) return null;
  return (
    <div className="aim-alert-strip">
      {alerts.map((a, i) => (
        <div key={i} className="aim-alert-item">
          <span className="aim-alert-icon">⚠</span>
          {a}
        </div>
      ))}
    </div>
  );
}

function FeedCard({ entry, isLatest }: { entry: FeedEntry; isLatest: boolean }) {
  const time = new Date(entry.timestamp_ms).toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <div
      className={`aim-feed-card ${isLatest ? "aim-feed-card--latest" : ""}`}
      style={{
        borderLeft: `3px solid ${statusColor(entry.overall_status)}`,
        opacity: isLatest ? 1 : 0.6,
      }}
    >
      <div className="aim-card-header">
        <StatusBadge status={entry.overall_status} />
        <span className="aim-card-headline">{entry.headline}</span>
        <span className="aim-card-time">{time}</span>
      </div>

      {entry.recommended_action && entry.recommended_action !== "CONTINUE" && (
        <div
          style={{
            fontSize: 10, fontWeight: 800, letterSpacing: "0.05em", textTransform: "uppercase",
            color: ACTION_COLOR[entry.recommended_action] ?? "var(--text-1)",
            fontFamily: "var(--mono)", margin: "2px 0 6px",
          }}
        >
          → {entry.recommended_action.replace(/_/g, " ")}
        </div>
      )}

      <AlertStrip alerts={entry.alerts} />

      <ul className="aim-updates-list">
        {entry.updates.map((u, i) => (
          <li key={i} className="aim-update-item">
            <span className="aim-update-dot" />
            {u}
          </li>
        ))}
      </ul>

      <div style={{ fontSize: 8.5, color: PROVIDER_COLOR[entry.provider] ?? "var(--text-2)", marginTop: 6, letterSpacing: "0.03em" }}>
        {PROVIDER_LABEL[entry.provider] ?? entry.provider}
      </div>
    </div>
  );
}

interface Props {
  feed: FeedEntry[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onClear: () => void;
  maxVisible?: number;
}

export default function AiMonitorFeed({ feed, loading, error, onRetry, onClear, maxVisible }: Props) {
  const latestStatus = feed[0]?.overall_status ?? "NOMINAL";
  const latestProvider = feed[0]?.provider;
  const visible = maxVisible ? feed.slice(0, maxVisible) : feed;

  return (
    <div className="aim-root">
      <div className="aim-header" style={{ borderBottom: `2px solid ${statusColor(latestStatus)}30` }}>
        <div className="aim-header-left">
          <span className="aim-title">🤖 AI Mission Monitor</span>
          <span className="aim-subtitle" style={{ color: latestProvider ? PROVIDER_COLOR[latestProvider] : undefined }}>
            {latestProvider ? PROVIDER_LABEL[latestProvider] : "updates every 4 s"}
          </span>
        </div>
        <div className="aim-header-right">
          {loading && (
            <span className="aim-spinner" title="Fetching update…">
              <span className="connecting-ring" style={{ width: 10, height: 10 }} />
              Updating…
            </span>
          )}
          {feed.length > 0 && <StatusBadge status={latestStatus} />}
        </div>
      </div>

      {error && (
        <div className="aim-error">
          <span>⚠ {error}</span>
          <button className="aim-retry-btn" onClick={onRetry}>Retry</button>
        </div>
      )}

      {feed.length === 0 && !error && (
        <div className="aim-empty">
          <div style={{ fontSize: 32, marginBottom: 8 }}>🤖</div>
          <div>Waiting for first AI monitor update…</div>
          <div className="aim-empty-sub">Collecting telemetry</div>
        </div>
      )}

      <div className="aim-feed">
        {visible.map((entry, idx) => (
          <FeedCard key={entry.id} entry={entry} isLatest={idx === 0} />
        ))}
      </div>

      {feed.length > 0 && (
        <div className="aim-footer">
          <span>Showing {visible.length} of last {feed.length}</span>
          <button className="aim-clear-btn" onClick={onClear}>Clear feed</button>
        </div>
      )}
    </div>
  );
}
