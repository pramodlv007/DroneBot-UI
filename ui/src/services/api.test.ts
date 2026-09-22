import { afterEach, expect, it, vi } from "vitest";
import { api } from "./api";

afterEach(() => vi.unstubAllGlobals());
it("shows actionable backend error details", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:"Connect both robots before starting."}), {status:409})));
  await expect(api.pauseMission()).rejects.toThrow("Connect both robots before starting.");
});
it("formats validation errors without raw HTTP payloads", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:[{msg:"Choose different robots."}]}), {status:422})));
  await expect(api.pauseMission()).rejects.toThrow("Choose different robots.");
});
it("does not show an HTML proxy failure as operator instructions", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>Proxy failure</html>", {status:502})));
  await expect(api.pauseMission()).rejects.toThrow("Request failed (502). Please try again.");
});
