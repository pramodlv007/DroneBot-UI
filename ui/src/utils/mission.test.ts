import { describe, expect, it } from "vitest";
import { isActiveMission, startBlockReason } from "./mission";

const robots = { leader: { connected: true }, follower: { connected: true } };
describe("mission readiness", () => {
  it.each(["RUNNING", "PAUSED", "DEGRADED", "EMERGENCY", "ARMED"] as const)("keeps %s in the active mission flow", state => {
    expect(isActiveMission(state)).toBe(true);
    expect(startBlockReason(state, true, "leader", "follower", robots)).toMatch(/Stop the current mission/);
  });
  it("explains that disconnected gateways block commands", () => {
    expect(startBlockReason("READY", false, "leader", "follower", robots)).toMatch(/gateway connection/);
  });
  it("requires two connected robots", () => {
    expect(startBlockReason("READY", true, "leader", "follower", {})).toMatch(/Connect two robots/);
  });
  it("requires two distinct role selections", () => {
    expect(startBlockReason("READY", true, "", "", robots)).toMatch(/Choose a leader/);
    expect(startBlockReason("READY", true, "leader", "leader", robots)).toMatch(/different robot/);
  });
  it("does not allow a previously selected disconnected robot", () => {
    expect(startBlockReason("READY", true, "leader", "missing", robots)).toMatch(/Both selected robots/);
  });
  it("allows a fresh mission after stop", () => {
    expect(isActiveMission("STOPPED")).toBe(false);
    expect(startBlockReason("STOPPED", true, "leader", "follower", robots)).toBeNull();
  });
});
