import { useSearchParams } from "react-router-dom";
import ConnectionPanel from "@/components/ConnectionPanel";
import MissionMap from "@/components/MissionMap";
import RobotsPanel from "@/components/RobotsPanel";
import CoordinationPanel from "@/components/CoordinationPanel";
import Timeline from "@/components/Timeline";
import SupervisorPanel from "@/components/SupervisorPanel";
import MissionControls from "@/components/MissionControls";
import { useCoordinationStore } from "@/stores/coordinationStore";
import { fmtNum } from "@/utils/format";

export default function MissionControlPage() {
  const [params, setParams] = useSearchParams();
  const coordination = useCoordinationStore(s => s.coordination);
  if (params.get("view") !== "mission") {
    return <ConnectionPanel onProceed={() => setParams({ view: "mission" })} />;
  }
  return <>
    <div className="mission-toolbar"><h1>Mission</h1><button onClick={() => setParams({ view: "connections" })}>Connections</button></div>
    <div className="mission-workspace">
      <MissionMap />
      <aside className="mission-sidebar" aria-label="Team status">
        <RobotsPanel />
        <div className="tracking-summary">
          <h2>Tracking <span>{coordination.state.toLowerCase()}</span></h2>
          <dl><div><dt>Separation</dt><dd>{coordination.leader_id ? fmtNum(coordination.separation_m, 1, " m") : "—"}</dd></div>
            <div><dt>Tracking error</dt><dd>{fmtNum(coordination.tracking_error_m, 2, " m")}</dd></div></dl>
          <details className="quiet-details"><summary>Coordination details</summary><CoordinationPanel /></details>
        </div>
        <details className="quiet-details"><summary>Activity log</summary><Timeline /></details>
        <details className="quiet-details"><summary>AI recommendations</summary><SupervisorPanel /></details>
      </aside>
    </div>
    <MissionControls />
  </>;
}
