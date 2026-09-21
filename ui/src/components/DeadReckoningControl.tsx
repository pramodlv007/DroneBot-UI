import { useState } from "react";
import { api } from "@/services/api";
import type { DeadReckoningInfo } from "@/types/robot";

interface Props {
  robotId: string;
  info: DeadReckoningInfo;
  connected: boolean;
  isMock: boolean;
}

/**
 * Indoor/GPS-denied tracking control — sleek compact design with smooth scrolling.
 * Lets an operator opt in to dead-reckoning position when GPS has no fix indoors,
 * and re-zero it against a known point.
 */
export default function DeadReckoningControl({ robotId, info, connected, isMock }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  // Local only — the registry doesn't expose current fault-injection state,
  // and this button only exists in SIMULATION mode anyway.
  const [gpsLossInjected, setGpsLossInjected] = useState(false);

  async function toggle() {
    setBusy(true);
    setError(null);
    try {
      await api.setDeadReckoning(robotId, !info.enabled);
    } catch (e: any) {
      setError("Toggle failed");
    } finally {
      setBusy(false);
    }
  }

  async function resetOrigin() {
    setBusy(true);
    setError(null);
    try {
      await api.resetDeadReckoning(robotId);
    } catch (e: any) {
      setError("Reset failed");
    } finally {
      setBusy(false);
    }
  }

  async function toggleGpsLoss() {
    setBusy(true);
    setError(null);
    try {
      if (gpsLossInjected) {
        await api.clearFault(robotId);
      } else {
        await api.injectFault(robotId, { gps_loss: true });
      }
      setGpsLossInjected(!gpsLossInjected);
    } catch (e: any) {
      setError("Fault injection failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="dead-reckoning-box">
      <div className="dead-reckoning-header" onClick={() => setExpanded(!expanded)}>
        <div className="dead-reckoning-title-wrap">
          <span className="dead-reckoning-icon">🧭</span>
          <span className="dead-reckoning-title">Dead-Reckoning</span>
          {info.active ? (
            <span className="badge WARNING" style={{ fontSize: 8, padding: "1px 5px" }}>ACTIVE</span>
          ) : info.enabled ? (
            <span className="badge NORMAL" style={{ fontSize: 8, padding: "1px 5px" }}>ARMED</span>
          ) : null}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }} onClick={(e) => e.stopPropagation()}>
          <label className="toggle-switch" title={info.enabled ? "Disable dead reckoning" : "Enable dead reckoning"}>
            <input
              type="checkbox"
              checked={info.enabled}
              disabled={busy || !connected}
              onChange={toggle}
            />
            <span className="slider" />
          </label>
          <button
            type="button"
            className="dr-expand-btn"
            onClick={() => setExpanded(!expanded)}
            title={expanded ? "Collapse details" : "Expand details"}
          >
            {expanded ? "▲" : "▼"}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="dead-reckoning-body">
          <div className="dead-reckoning-desc">
            {info.active
              ? "⚠ Position is estimated from heading & ground speed (drifts over time without GPS)."
              : info.enabled
              ? "Armed: Will engage automatically if GPS 3D fix is lost."
              : "Disabled: Uses heading & ground speed when GPS is unavailable."}
          </div>
          {info.enabled && (
            <button
              type="button"
              className="dr-reset-btn"
              onClick={resetOrigin}
              disabled={busy || !connected}
              title="Re-zero the drift-accumulating estimate at the current position"
            >
              ⟲ RESET ESTIMATE ORIGIN
            </button>
          )}
          {isMock && (
            <button
              type="button"
              className="dr-reset-btn"
              onClick={toggleGpsLoss}
              disabled={busy || !connected}
              title="Simulation-only: force the mock drone's GPS fix to drop so you can see dead reckoning engage without waiting for the scripted scenario cycle"
            >
              {gpsLossInjected ? "✕ CLEAR SIMULATED GPS LOSS" : "🧪 SIMULATE GPS LOSS (TEST)"}
            </button>
          )}
          {error && <div className="dr-error">{error}</div>}
        </div>
      )}
    </div>
  );
}
