import { useState, type CSSProperties } from "react";
import { api } from "@/services/api";
import type { RegisteredRobot } from "@/types/robot";

interface Props {
  robot: RegisteredRobot;
  onSaved: () => void;
}

// Editable connection linkage for a robot, so an operator can point the
// gateway at real hardware without hand-editing config/robots.yaml and
// restarting the backend. MAVLink robots are directly configurable here
// (the gateway dials out to them). ROS2/TurtleBot robots are the other
// direction — the robot's ros_node dials INTO the gateway — so instead of
// an editable field this generates the exact `ros2 launch` command to run
// on the robot's companion computer, with the gateway's own address
// filled in automatically.
export default function RobotConnectionSettings({ robot, onSaved }: Props) {
  if (robot.protocol === "MAVLink") {
    return <MavlinkSettings robot={robot} onSaved={onSaved} />;
  }
  if (robot.protocol === "ROS2") {
    return <Ros2LaunchHelper robot={robot} />;
  }
  return null;
}

function MavlinkSettings({ robot, onSaved }: Props) {
  const [connection, setConnection] = useState(robot.connection.connection ?? "");
  const [baud, setBaud] = useState(String(robot.connection.baud ?? 57600));
  const [targetSystem, setTargetSystem] = useState(String(robot.connection.targetSystem ?? 1));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await api.updateRobotConfig(robot.robotId, {
        connection,
        baud: Number(baud) || undefined,
        target_system: Number(targetSystem) || undefined,
      });
      onSaved();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{ marginTop: 12, textAlign: "left", borderTop: "1px solid var(--border)", paddingTop: 10 }}>
      <div style={{ fontSize: 10, color: "var(--text-2)", textTransform: "uppercase", marginBottom: 6 }}>
        MAVLink connection
      </div>
      <label style={fieldLabel}>
        Connection string
        <input
          style={fieldInput}
          value={connection}
          placeholder='"COM10" or "udp:0.0.0.0:14550"'
          onChange={(e) => setConnection(e.target.value)}
        />
      </label>
      <label style={fieldLabel}>
        Baud (serial only)
        <input style={fieldInput} value={baud} onChange={(e) => setBaud(e.target.value)} />
      </label>
      <label style={fieldLabel}>
        Target system id
        <input style={fieldInput} value={targetSystem} onChange={(e) => setTargetSystem(e.target.value)} />
      </label>
      {error && <div style={{ color: "var(--crit)", fontSize: 10, marginTop: 4 }}>{error}</div>}
      <button className="primary" style={{ width: "100%", marginTop: 8 }} disabled={saving || !connection} onClick={save}>
        {saving ? "SAVING..." : "SAVE"}
      </button>
      <div style={{ fontSize: 9.5, color: "var(--text-2)", marginTop: 6 }}>
        Takes effect on next CONNECT. Not persisted to config/robots.yaml —
        edit that file directly if you want it to survive a gateway restart.
      </div>
    </div>
  );
}

function Ros2LaunchHelper({ robot }: { robot: RegisteredRobot }) {
  const [headingDeg, setHeadingDeg] = useState("0");
  const [gatewayHost, setGatewayHost] = useState(window.location.hostname);
  const [gatewayPort, setGatewayPort] = useState("8000");
  const [copied, setCopied] = useState(false);

  const command = [
    "ros2 launch heterogeneous_robot_bridge turtlebot_bridge.launch.py",
    `  robot_id:=${robot.robotId}`,
    `  gateway_ws_url:=ws://${gatewayHost}:${gatewayPort}/ws/ingest`,
    `  heading_deg_from_north:=${headingDeg || "0"}`,
  ].join(" \\\n");

  async function copy() {
    await navigator.clipboard.writeText(command);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div style={{ marginTop: 12, textAlign: "left", borderTop: "1px solid var(--border)", paddingTop: 10 }}>
      <div style={{ fontSize: 10, color: "var(--text-2)", textTransform: "uppercase", marginBottom: 6 }}>
        ROS2 launch command
      </div>
      <div style={{ fontSize: 10.5, color: "var(--text-1)", marginBottom: 8 }}>
        This robot's ROS2 node connects <em>out</em> to the gateway — there's
        nothing to configure here in the browser. Run this on the TurtleBot's
        companion computer, then click CONNECT.
      </div>

      <label style={fieldLabel}>
        Gateway host (reachable from the robot)
        <input style={fieldInput} value={gatewayHost} onChange={(e) => setGatewayHost(e.target.value)} />
      </label>
      <label style={fieldLabel}>
        Gateway port
        <input style={fieldInput} value={gatewayPort} onChange={(e) => setGatewayPort(e.target.value)} />
      </label>
      <label style={fieldLabel}>
        Heading (° from North the robot's front faces at boot)
        <input style={fieldInput} value={headingDeg} onChange={(e) => setHeadingDeg(e.target.value)} />
      </label>

      <pre
        className="mono"
        style={{
          background: "var(--bg-3)",
          border: "1px solid var(--border)",
          borderRadius: 6,
          padding: 8,
          fontSize: 10,
          whiteSpace: "pre-wrap",
          wordBreak: "break-all",
          marginTop: 6,
        }}
      >
        {command}
      </pre>
      <button style={{ width: "100%", marginTop: 6 }} onClick={copy}>
        {copied ? "COPIED ✓" : "COPY COMMAND"}
      </button>
    </div>
  );
}

const fieldLabel: CSSProperties = {
  display: "block",
  fontSize: 10.5,
  color: "var(--text-2)",
  marginBottom: 6,
};

const fieldInput: CSSProperties = {
  display: "block",
  width: "100%",
  marginTop: 3,
  padding: "5px 7px",
  background: "var(--bg-3)",
  border: "1px solid var(--border-strong)",
  borderRadius: 5,
  color: "var(--text-0)",
  fontFamily: "var(--mono)",
  fontSize: 11,
};
