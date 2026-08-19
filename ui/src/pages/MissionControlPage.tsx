import { useEffect, useState } from "react";
import { api } from "@/services/api";
import ConnectionPanel from "@/components/ConnectionPanel";
import MissionMap from "@/components/MissionMap";
import RobotsPanel from "@/components/RobotsPanel";
import CoordinationPanel from "@/components/CoordinationPanel";
import Timeline from "@/components/Timeline";
import SupervisorPanel from "@/components/SupervisorPanel";
import MissionControls from "@/components/MissionControls";

export default function MissionControlPage() {
  // Robots are not assumed to always be available (§18) — poll the
  // registry (not live telemetry, which only exists once already
  // connected) to decide whether to show the connection screen or the
  // mission view. The operator can also dismiss the connection screen
  // early via "Skip" to connect additional robots later from a partial
  // mission view.
  const [connectedCount, setConnectedCount] = useState<number | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    let mounted = true;
    async function poll() {
      try {
        const robots = await api.listRobots();
        if (mounted) setConnectedCount(robots.filter((r) => r.connected).length);
      } catch {
        /* transient */
      }
    }
    poll();
    const interval = setInterval(poll, 2000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  const showConnectionScreen = !dismissed && (connectedCount === null || connectedCount < 2);

  if (showConnectionScreen) {
    return (
      <>
        <ConnectionPanel onAllConnected={() => setDismissed(true)} />
        {connectedCount !== null && connectedCount > 0 && (
          <div style={{ textAlign: "center", paddingBottom: 24 }}>
            <button onClick={() => setDismissed(true)}>Continue with {connectedCount} robot(s) connected →</button>
          </div>
        )}
      </>
    );
  }

  return (
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
  );
}
