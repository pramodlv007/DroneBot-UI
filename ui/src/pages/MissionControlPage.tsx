import { useState } from "react";
import ConnectionPanel from "@/components/ConnectionPanel";
import MissionMap from "@/components/MissionMap";
import RobotsPanel from "@/components/RobotsPanel";
import CoordinationPanel from "@/components/CoordinationPanel";
import Timeline from "@/components/Timeline";
import SupervisorPanel from "@/components/SupervisorPanel";
import MissionControls from "@/components/MissionControls";
import LiveMetricsBar from "@/components/LiveMetricsBar";
import AiMonitorTab from "@/components/AiMonitorTab";

type MissionTab = "overview" | "ai-monitor";

export default function MissionControlPage() {
  const [dismissed, setDismissed] = useState(false);
  const [activeTab, setActiveTab] = useState<MissionTab>("overview");

  if (!dismissed) {
    return <ConnectionPanel onProceed={() => setDismissed(true)} />;
  }

  return (
    <>
      {/* Always-visible live data strip */}
      <LiveMetricsBar />

      {/* ── Mission sub-navigation tab bar ── */}
      <div className="mission-tab-bar">
        <button
          id="mission-tab-overview"
          className={`mission-tab-btn${activeTab === "overview" ? " mission-tab-btn--active" : ""}`}
          onClick={() => setActiveTab("overview")}
        >
          📡 Mission Overview
        </button>
        <button
          id="mission-tab-ai-monitor"
          className={`mission-tab-btn${activeTab === "ai-monitor" ? " mission-tab-btn--active" : ""}`}
          onClick={() => setActiveTab("ai-monitor")}
        >
          🤖 AI Monitor
        </button>
      </div>

      {/* ── Tab panels ── */}
      {activeTab === "overview" && (
        <>
          <div className="main-grid">
            <MissionMap />
            <RobotsPanel />
            <CoordinationPanel />
            <Timeline />
            <SupervisorPanel />
          </div>
          <MissionControls />
        </>
      )}

      <AiMonitorTab isActive={activeTab === "ai-monitor"} />
    </>
  );
}
