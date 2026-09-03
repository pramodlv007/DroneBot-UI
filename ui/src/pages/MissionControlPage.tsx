import { useState } from "react";
import ConnectionPanel from "@/components/ConnectionPanel";
import MissionMap from "@/components/MissionMap";
import RobotsPanel from "@/components/RobotsPanel";
import CoordinationPanel from "@/components/CoordinationPanel";
import Timeline from "@/components/Timeline";
import SupervisorPanel from "@/components/SupervisorPanel";
import MissionControls from "@/components/MissionControls";
import LiveMetricsBar from "@/components/LiveMetricsBar";

export default function MissionControlPage() {
  const [dismissed, setDismissed] = useState(false);

  if (!dismissed) {
    return <ConnectionPanel onProceed={() => setDismissed(true)} />;
  }

  return (
    <>
      {/* Always-visible live data strip */}
      <LiveMetricsBar />

      <div className="main-grid">
        <MissionMap />
        <RobotsPanel />
        <CoordinationPanel />
        <Timeline />
        <SupervisorPanel />
      </div>
      <MissionControls />
    </>
  );
}
