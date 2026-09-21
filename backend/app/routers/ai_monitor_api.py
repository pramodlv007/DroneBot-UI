"""
AI Mission Monitor — POST /api/ai-monitor/update

Accepts a full telemetry snapshot from the UI (robots, coordination, mission,
system_health), calls GPT-4o-mini to produce human-readable operator updates,
and returns a structured JSON the AiMonitorTab component can render directly.

Monitored cases (explicitly in the system prompt):
  - Emergency stop — mission.state == EMERGENCY always wins, always STOP
  - Battery levels — drone and TurtleBot (warn < 30 %, critical < 15 %)
  - Active anomalies — AnomalyDetector's live STUCK/HEADING_OSCILLATION
    state (backend/app/anomaly_detector.py), plus its point-in-time
    BATTERY_DRAIN/POSITION_JUMP events surfaced separately as toasts —
    the AI monitor treats an active anomaly as authoritative, not
    something to re-derive from raw velocity itself
  - Dead reckoning — flag when a robot's position is an ESTIMATE (no GPS
    fix) rather than measured, since that changes how much to trust the
    map, not just whether the robot is "healthy"
  - Separation distance — actual vs target (warn if > 2× target)
  - Predictive separation — backend-computed 3s-ahead extrapolation and
    trend (CONVERGING/STABLE/DIVERGING); a DIVERGING trend is a leading
    indicator worth a proactive note even before the threshold is crossed
  - Mission health score — the backend's weighted 0-100 composite and
    which single factor (tracking/latency/battery/gps/safety) is
    dragging it down, so the operator doesn't have to reconstruct that
    from five separate numbers
  - Robots stuck / stalled — a lightweight velocity≈0 heuristic as a
    fallback for cases the AnomalyDetector isn't tracking (e.g. IDLE
    robots), clearly secondary to the "Active anomalies" signal above
  - GPS quality — drone fix type < 3
  - Telemetry lag — source vs received timestamp delta > 300 ms
  - Tracking error — coordination tracking_error_m (warn > 1.5 m)
  - System health — surface CRITICAL / WARNING immediately
  - Flight mode anomaly — unexpected drone mode
  - Mission duration — flag unusually long missions

Also returns `recommended_action`, reusing the same vocabulary as the
separate always-on MissionSupervisor (app/supervisor/*, SupervisorPanel)
so an operator sees one consistent action vocabulary regardless of which
of the two systems produced it — CONTINUE / SLOW_DOWN / PAUSE / STOP /
CHECK_GPS / CHECK_COMMUNICATION / RETURN_TO_SAFE_STATE.

Falls back to a deterministic rule-based summary when OPENAI_API_KEY is not
set so the UI still works in simulation / dev environments with no key.
"""

from __future__ import annotations

import json
import logging
import math
import time
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.models import RecommendedAction

logger = logging.getLogger("ai_monitor")

router = APIRouter(prefix="/api/ai-monitor", tags=["ai-monitor"])

# A permanently-failing key (quota exhausted, revoked, invalid) fails the
# same way on every retry. The AI Monitor tab polls this endpoint every 4s,
# and each real network round-trip to a dead key costs multiple seconds —
# tying up that time repeatedly risks starving the shared event loop the
# control loop (and simulated robot telemetry) also runs on. Once we've
# seen a hard auth/quota failure, skip straight to the instant rule-based
# fallback for a cooldown window instead of re-attempting every poll.
# Tracked per-provider so a dead OpenAI key doesn't also block a working
# Anthropic one, or vice versa.
_LLM_COOLDOWN_S = 300.0
_openai_disabled_until = 0.0
_claude_disabled_until = 0.0

# ─── Pydantic I/O models ─────────────────────────────────────────────────────

class MonitorRequest(BaseModel):
    robots: dict[str, Any] = {}
    coordination: dict[str, Any] = {}
    mission: dict[str, Any] = {}
    system_health: dict[str, Any] = {}
    # robot_id -> currently-active anomaly types, from AnomalyDetector.active_anomalies()
    anomalies: dict[str, list[str]] = {}


class MonitorResponse(BaseModel):
    headline: str
    updates: list[str]
    alerts: list[str]
    overall_status: str          # "NOMINAL" | "WARNING" | "CRITICAL"
    # Same vocabulary as SupervisorRecommendation.recommended_action, so the
    # UI and the operator see one consistent action language regardless of
    # which of the two AI systems produced it.
    recommended_action: str = "CONTINUE"
    # Which engine actually produced this response — surfaced in the UI so
    # it's never ambiguous whether you're looking at real LLM reasoning or
    # the deterministic threshold-checking fallback (they read very
    # differently, and that difference should never be silent).
    provider: str = "rule_based"
    timestamp_ms: int


_ALLOWED_ACTIONS = {a.value for a in RecommendedAction}


# ─── System prompt ───────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are the mission-monitoring agent for a heterogeneous aerial-ground
robot team (one UAV drone, one UGV TurtleBot), acting as a second set of eyes
for a human operator who cannot watch every number at once. You are not a
telemetry dashboard and you must never behave like one.

DO NOT simply restate raw values ("Separation: 1.60 m", "Latency: 50 ms").
The operator can already see those numbers elsewhere. Your job is to
INTERPRET them: is this normal, and how do you know? Is it trending toward
a problem? What, specifically, should the operator do right now, and why?
Every line you write should answer "so what?" — if a value is unremarkable,
say so briefly or omit it; do not pad the report with numbers restated as
sentences.

If there is no active mission (mission.state is one of DISCONNECTED, READY,
ARMED, STOPPED, COMPLETED) and no robots are connected, do not manufacture
observations from empty/zeroed fields. Say plainly that you are standing by
and what's needed to start monitoring (e.g. "No active mission — connect
both robots and assign leader/follower roles to begin"). If robots ARE
connected but no mission has started, you may give a brief pre-flight
readiness read (battery, GPS, connectivity) without inventing coordination
data that doesn't exist yet (no leader/follower assigned means separation
and tracking error are meaningless — don't mention them).

MONITORING PRIORITIES (check every update cycle, highest priority first):
1. EMERGENCY STOP — If mission.state == "EMERGENCY", this overrides
   everything else: overall_status is CRITICAL and recommended_action is
   STOP, regardless of any other field.
2. ACTIVE ANOMALIES — The `anomalies` field maps robot_id to a list of
   currently-ongoing conditions detected by the backend's own anomaly
   detector (e.g. "STUCK", "HEADING_OSCILLATION"). Treat these as
   authoritative ground truth, not something to second-guess from raw
   velocity — always surface them as alerts.
3. BATTERY — Drone battery: CRITICAL < 15 %, WARNING < 30 %.
             TurtleBot battery: CRITICAL < 15 %, WARNING < 30 %.
4. DEAD RECKONING — If a robot's metadata.dead_reckoning_active is true,
   its position is an ESTIMATE from heading+speed integration, not a
   measured GPS/EKF position, and drifts over time. Mention this as a
   distinct caution — it's about how much to trust the position, not
   about robot health.
5. SEPARATION — Actual separation vs target. WARNING if actual > 2× target.
               CRITICAL if separation > 4 m when mission is RUNNING.
6. PREDICTIVE SEPARATION — coordination.predicted_separation_m /
   predicted_tracking_error_m extrapolate ~3s ahead from current
   velocity; coordination.separation_trend is CONVERGING/STABLE/DIVERGING.
   A DIVERGING trend heading toward the threshold is worth a proactive
   note even if the current separation is still fine.
7. MISSION HEALTH SCORE — coordination.mission_health_score (0-100) and
   mission_health_components (tracking/latency/battery/gps/safety
   sub-scores). If the composite is below ~60, name the single lowest
   component rather than just restating the score.
8. ROBOTS STUCK (fallback) — Only if a robot has no active STUCK anomaly
   from the detector: if mission state is RUNNING but its velocity is
   near zero (< 0.05 m/s linear), flag as "possible stall — check for
   obstacles". This is a weaker, secondary signal versus priority 2.
9. GPS — Drone GPS fix type: WARNING if fix < 3 (no reliable position).
10. TELEMETRY LAG — Difference between source_timestamp_ms and
                   received_timestamp_ms. WARNING if > 300 ms.
11. TRACKING ERROR — coordination.tracking_error_m: WARNING > 1.5 m,
                    CRITICAL > 3 m.
12. SYSTEM HEALTH — If overall health is CRITICAL or WARNING, surface it.
13. FLIGHT MODE — Note the drone's current mode. Warn if it is unexpected
                 (e.g. LAND or LOITER when mission is RUNNING).
14. MISSION DURATION — If started_at_ms is set, compute elapsed time and
                      mention it naturally. Flag missions running > 30 min.
15. GENERAL — Any other observations that an operator would want to know.

RESPONSE FORMAT — return ONLY valid JSON, no markdown, no prose outside JSON:
{
  "headline": "<concise one-liner <= 12 words>",
  "updates": ["<observation 1>", "<observation 2>", ...],
  "alerts": ["<alert text>", ...],
  "overall_status": "NOMINAL" | "WARNING" | "CRITICAL",
  "recommended_action": "CONTINUE" | "SLOW_DOWN" | "PAUSE" | "STOP" | "CHECK_GPS" | "CHECK_COMMUNICATION" | "RETURN_TO_SAFE_STATE"
}

Rules:
- updates: 2-6 evaluative statements, each pairing a judgment with its
  reason — "Battery healthy at 82%, no drain concern" not "Battery: 82%".
  Fewer, meaningful lines beat a longer list of restated numbers. If
  nothing at all is noteworthy, one line ("All systems nominal, nothing
  requires attention") is correct and preferred over padding.
- alerts: only include if something needs operator attention, and say
  what to check or do about it, not just that a threshold was crossed.
- overall_status: CRITICAL if emergency stop is active, any battery < 15 %,
  tracking_error > 3 m, or system health is CRITICAL. WARNING if any
  warning threshold is breached. NOMINAL otherwise.
- recommended_action must be exactly one of the seven listed values —
  never invent a new action, and never reference a specific velocity,
  motor command, or actuator call. This is advisory text for a human
  operator, not a command that gets executed automatically.
- Never fabricate data. If a field is null/missing, say "data unavailable"
  rather than guessing — but also don't report on fields that are
  structurally absent because no mission is active (see above).
- Keep language terse and professional — this is an ops display, not a
  chat — but terse means information-dense, not just short: "Tracking
  degrading, separation growing 0.4 m over the last cycle — recommend
  slowing the leader" is one terse, useful sentence; "Separation: 1.9 m"
  is a short but useless one.
"""

# ─── Deterministic fallback (no API key) ─────────────────────────────────────

def _now_ms() -> int:
    return int(time.time() * 1000)


_ACTION_RANK = {
    "CONTINUE": 0,
    "CHECK_COMMUNICATION": 1,
    "CHECK_GPS": 1,
    "SLOW_DOWN": 2,
    "PAUSE": 3,
    "RETURN_TO_SAFE_STATE": 4,
    "STOP": 5,
}


def _rule_based_monitor(req: MonitorRequest) -> MonitorResponse:
    """Pure Python rule engine — no LLM. Used when OPENAI_API_KEY is absent
    (or the LLM path is in cooldown after a hard failure)."""
    updates: list[str] = []
    alerts: list[str] = []
    worst = "NOMINAL"
    action = "CONTINUE"

    def escalate(new_worst: str) -> None:
        nonlocal worst
        if new_worst == "CRITICAL" or worst == "NOMINAL":
            worst = new_worst

    def recommend(candidate: str) -> None:
        nonlocal action
        if _ACTION_RANK[candidate] > _ACTION_RANK[action]:
            action = candidate

    now = _now_ms()
    mission = req.mission
    coord = req.coordination

    m_state = mission.get("state", "DISCONNECTED")
    coordination_active = coord.get("leader_id") is not None and coord.get("follower_id") is not None
    idle_states = ("DISCONNECTED", "READY", "ARMED", "STOPPED", "COMPLETED")

    if m_state == "EMERGENCY":
        alerts.append("EMERGENCY STOP is active — all motion commands are being blocked")
        escalate("CRITICAL")
        recommend("STOP")
    elif m_state in idle_states and not req.robots:
        # Nothing connected, nothing running — say so plainly instead of
        # manufacturing observations from empty/zeroed telemetry fields.
        updates.append("Standing by — no robots connected. Connect drone_01 and turtlebot_01 to begin monitoring.")
    elif m_state in idle_states and not coordination_active:
        updates.append(f"Robots connected but no mission active ({m_state}) — assign leader/follower roles and start a mission for full coordination monitoring.")
    else:
        started = mission.get("started_at_ms")
        if started:
            elapsed_s = (now - started) / 1000
            m, s = divmod(int(elapsed_s), 60)
            h, m = divmod(m, 60)
            dur = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
            updates.append(f"Mission {m_state}, running {dur}")
            if elapsed_s > 1800:
                alerts.append(f"Mission has been running for over 30 minutes ({dur}) — confirm this is expected")
                escalate("WARNING")
        else:
            updates.append(f"Mission state: {m_state}")

    # Active anomalies from the backend's own always-on detector — treated
    # as authoritative, ahead of any heuristic this rule engine re-derives.
    anomaly_hint = {
        "STUCK": "commanded to move but has barely displaced — possible obstacle, wheel slip, or stall",
        "HEADING_OSCILLATION": "heading keeps reversing direction — possible control instability",
    }
    for rid, kinds in req.anomalies.items():
        for kind in kinds:
            alerts.append(f"{rid}: {anomaly_hint.get(kind, kind)}")
            escalate("WARNING")
            recommend("PAUSE")

    # Per-robot checks
    for rid, rs in req.robots.items():
        rtype = rs.get("robot_type", "")
        label = "Drone" if rtype == "UAV" else "Bot"
        has_stuck_anomaly = "STUCK" in req.anomalies.get(rid, [])

        # Dead reckoning — a trust-in-position caution, not a health issue
        if (rs.get("metadata") or {}).get("dead_reckoning_active"):
            alerts.append(f"{label} position is an ESTIMATE (dead reckoning, no GPS fix) — expect drift")
            escalate("WARNING")

        # Battery
        batt = (rs.get("battery") or {}).get("percentage")
        if batt is not None:
            if batt < 15:
                alerts.append(f"{label} battery CRITICAL: {batt:.0f}%")
                escalate("CRITICAL")
                recommend("RETURN_TO_SAFE_STATE")
            elif batt < 30:
                alerts.append(f"{label} battery LOW: {batt:.0f}% — plan to land/dock soon")
                escalate("WARNING")
            elif batt < 50:
                updates.append(f"{label} battery at {batt:.0f}%, adequate but past the halfway point")

        # Telemetry lag — only worth a line when it's actually notable in
        # either direction, not restated every cycle when it's fine.
        src_ts = rs.get("source_timestamp_ms", 0)
        rcv_ts = rs.get("received_timestamp_ms", 0)
        lag = rcv_ts - src_ts
        if lag > 500:
            alerts.append(f"{label} telemetry lag HIGH ({lag:.0f} ms) — check network/link quality before trusting its latest position")
            escalate("WARNING")
            recommend("CHECK_COMMUNICATION")
        elif lag > 300:
            updates.append(f"{label} telemetry lag elevated at {lag:.0f} ms, within tolerance but worth watching")

        # GPS (drone only)
        if rtype == "UAV":
            gps = rs.get("gps")
            if gps:
                fix = gps.get("fix", 0)
                alt = gps.get("altitude", 0)
                if fix < 3:
                    alerts.append(f"Drone GPS fix weak: fix type {fix}")
                    escalate("WARNING")
                    recommend("CHECK_GPS")
                else:
                    updates.append(f"Drone altitude: {alt:.1f} m, GPS fix: {fix}")

            mode = rs.get("mode")
            if mode:
                updates.append(f"Drone flight mode: {mode}")
                if m_state == "RUNNING" and mode in ("LAND", "RTL", "LOITER"):
                    alerts.append(f"Unexpected drone mode during RUNNING mission: {mode}")
                    escalate("WARNING")

        # Stuck detection — fallback heuristic only when the detector isn't
        # already reporting STUCK for this robot (avoid double-counting).
        if not has_stuck_anomaly:
            vel = rs.get("velocity") or {}
            lx = abs(vel.get("linear_x", 0))
            ly = abs(vel.get("linear_y", 0))
            lz = abs(vel.get("linear_z", 0))
            speed = math.sqrt(lx**2 + ly**2 + lz**2)
            if m_state == "RUNNING" and speed < 0.05:
                alerts.append(f"{label} appears stationary while mission is RUNNING — possible stall")
                escalate("WARNING")

    # Pair-level coordination metrics only mean something once a
    # leader/follower pair is actually assigned — separation/tracking error
    # are 0.00 by construction otherwise, which is not information.
    if coordination_active:
        sep = coord.get("separation_m")
        target_sep = coord.get("target_separation_m") or 1.5
        if sep is not None:
            if sep > 4.0 and m_state == "RUNNING":
                alerts.append(f"Separation CRITICAL at {sep:.2f} m (limit ~4 m) — follower is losing the leader")
                escalate("CRITICAL")
                recommend("PAUSE")
            elif sep > target_sep * 2:
                alerts.append(f"Separation running high: {sep:.2f} m vs a {target_sep:.1f} m target — follower is falling behind")
                escalate("WARNING")
                recommend("SLOW_DOWN")
            else:
                updates.append(f"Holding formation: {sep:.2f} m separation, close to the {target_sep:.1f} m target")

        # Predictive separation — a leading indicator, checked even if the
        # current separation is still fine.
        pred_err = coord.get("predicted_tracking_error_m")
        trend = coord.get("separation_trend")
        pred_sep = coord.get("predicted_separation_m")
        if pred_err is not None and trend == "DIVERGING":
            if pred_err >= 2.0:
                detail = f"~{pred_sep:.1f} m in 3s" if pred_sep is not None else "worsening"
                alerts.append(f"Separation is diverging and projected to reach {detail} — act before it crosses the threshold, not after")
                escalate("WARNING")
                recommend("SLOW_DOWN")
            else:
                updates.append("Separation trending apart but still within margin — worth watching, not yet actionable")

        # Mission health score — name the weakest factor and say what that
        # means, not just the number.
        health_score = coord.get("mission_health_score")
        health_components = coord.get("mission_health_components") or {}
        if health_score is not None and health_score < 85:
            if health_components:
                worst_factor = min(health_components, key=lambda k: health_components[k])
                updates.append(
                    f"Mission health {health_score:.0f}/100, dragged down mainly by {worst_factor} "
                    f"({health_components[worst_factor]:.0f}/100)"
                )
            else:
                updates.append(f"Mission health {health_score:.0f}/100")
            if health_score < 40:
                escalate("CRITICAL")
            elif health_score < 60:
                escalate("WARNING")

        # Tracking error
        err = coord.get("tracking_error_m")
        if err is not None:
            if err > 3.0:
                alerts.append(f"Tracking error CRITICAL at {err:.2f} m — follower is not converging on target separation")
                escalate("CRITICAL")
                recommend("PAUSE")
            elif err > 1.5:
                alerts.append(f"Tracking error elevated at {err:.2f} m — follower is lagging the target separation")
                escalate("WARNING")
                recommend("SLOW_DOWN")

    # System health
    overall_health = req.system_health.get("overall", "UNKNOWN")
    if overall_health == "CRITICAL":
        alerts.append("System health: CRITICAL")
        escalate("CRITICAL")
        recommend("RETURN_TO_SAFE_STATE")
    elif overall_health == "WARNING":
        alerts.append("System health: WARNING")
        escalate("WARNING")

    if not updates:
        updates.append("No robot data available — waiting for telemetry")

    headline_map = {
        "CRITICAL": "⚠ Critical issues detected — immediate attention required",
        "WARNING": "⚡ Warnings present — monitor closely",
        "NOMINAL": "✓ All systems nominal",
    }

    return MonitorResponse(
        headline=headline_map[worst],
        updates=updates[:6],
        alerts=alerts,
        overall_status=worst,
        recommended_action=action,
        provider="rule_based",
        timestamp_ms=now,
    )


def _user_payload(req: MonitorRequest) -> str:
    return json.dumps(
        {
            "robots": req.robots,
            "coordination": req.coordination,
            "mission": req.mission,
            "system_health": req.system_health,
            "anomalies": req.anomalies,
            "current_timestamp_ms": _now_ms(),
        },
        default=str,
    )


def _parse_llm_json(data: dict, provider: str) -> MonitorResponse:
    action = data.get("recommended_action", "CONTINUE")
    if action not in _ALLOWED_ACTIONS:
        # Never trust the LLM's output blindly — an unrecognized action (or
        # one smuggling actuator-level text) downgrades to a safe,
        # conservative default rather than being surfaced as-is.
        action = "CONTINUE"
    return MonitorResponse(
        headline=data.get("headline", "Status update"),
        updates=data.get("updates", []),
        alerts=data.get("alerts", []),
        overall_status=data.get("overall_status", "NOMINAL"),
        recommended_action=action,
        provider=provider,
        timestamp_ms=_now_ms(),
    )


# ─── OpenAI-powered monitor ──────────────────────────────────────────────────

async def _openai_monitor(req: MonitorRequest, api_key: str, model: str) -> MonitorResponse | None:
    """Call GPT with the telemetry snapshot. Returns None (rather than
    falling back internally) so the endpoint can try the next configured
    provider before giving up to the rule engine.

    timeout/max_retries are deliberately tight: this runs on every poll of
    the AI Monitor tab (every 4s) in the same process as the control loop
    that keeps simulated/real robot telemetry flowing. An exhausted-quota
    or otherwise permanently-failing key would, with the SDK's default
    multi-minute timeout and automatic backoff retries, stall each poll for
    several seconds — long enough to starve the control loop and trip the
    staleness watchdog, disconnecting robots that never actually stopped
    sending telemetry. Retrying a quota/auth error also can't ever succeed,
    so there's no benefit to the default retry behavior here.
    """
    import openai
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, timeout=5.0, max_retries=0)

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _user_payload(req)},
            ],
            temperature=0.2,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        return _parse_llm_json(json.loads(raw), "openai")
    except openai.APIStatusError as exc:
        # Any 4xx (auth, billing/quota, malformed request, rate limit) is a
        # client-side problem retrying within a few minutes won't fix —
        # e.g. OpenAI's "insufficient_quota" comes back as 429. Broad range
        # rather than an enumerated list so a provider-specific billing code
        # we haven't seen before still gets a cooldown instead of being
        # retried every single poll (this is exactly the bug that let a
        # 400 "credit balance too low" slip through uncooled before).
        if 400 <= exc.status_code < 500:
            global _openai_disabled_until
            _openai_disabled_until = time.time() + _LLM_COOLDOWN_S
            logger.warning(
                "OpenAI monitor call failed with a non-retriable status (%s) — disabling for %.0fs (%s)",
                exc.status_code, _LLM_COOLDOWN_S, exc,
            )
        else:
            logger.warning("OpenAI monitor call failed (%s)", exc)
        return None
    except Exception as exc:
        logger.warning("OpenAI monitor call failed (%s)", exc)
        return None


# ─── Claude-powered monitor ──────────────────────────────────────────────────

async def _claude_monitor(req: MonitorRequest, api_key: str, model: str) -> MonitorResponse | None:
    """Call Claude with the telemetry snapshot. Same contract as
    _openai_monitor — returns None on any failure rather than falling back
    internally, and applies the same tight timeout/no-retry discipline for
    the same reason (see _openai_monitor's docstring)."""
    import anthropic
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key, timeout=5.0, max_retries=0)

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=600,
            system=_SYSTEM_PROMPT + "\nRespond with ONLY the JSON object described above, no other text.",
            messages=[{"role": "user", "content": _user_payload(req)}],
        )
        text = response.content[0].text
        return _parse_llm_json(json.loads(text), "claude")
    except anthropic.APIStatusError as exc:
        # See the matching comment in _openai_monitor — broad 4xx range
        # rather than an enumerated list, since Anthropic returns "credit
        # balance too low" as a plain 400, not 402/429 like you'd expect.
        if 400 <= exc.status_code < 500:
            global _claude_disabled_until
            _claude_disabled_until = time.time() + _LLM_COOLDOWN_S
            logger.warning(
                "Claude monitor call failed with a non-retriable status (%s) — disabling for %.0fs (%s)",
                exc.status_code, _LLM_COOLDOWN_S, exc,
            )
        else:
            logger.warning("Claude monitor call failed (%s)", exc)
        return None
    except Exception as exc:
        logger.warning("Claude monitor call failed (%s)", exc)
        return None


# ─── Endpoint ────────────────────────────────────────────────────────────────

@router.post("/update", response_model=MonitorResponse)
async def ai_monitor_update(body: MonitorRequest) -> MonitorResponse:
    """
    Analyze the current telemetry snapshot and return AI-generated operator
    updates. Tries OpenAI first, then Claude, in that order — whichever has
    a configured key and isn't in post-failure cooldown — and only falls
    back to the deterministic rule engine if neither is available or both
    fail. The response's `provider` field always says which one actually
    answered, so it's never ambiguous whether you're looking at real LLM
    reasoning or the rule-based fallback.
    """
    from app.config import get_settings

    settings = get_settings()
    now = time.time()

    if settings.openai_api_key and now >= _openai_disabled_until:
        result = await _openai_monitor(body, settings.openai_api_key, settings.openai_model or "gpt-4o-mini")
        if result is not None:
            return result

    if settings.anthropic_api_key and now >= _claude_disabled_until:
        result = await _claude_monitor(body, settings.anthropic_api_key, settings.anthropic_model or "claude-sonnet-5")
        if result is not None:
            return result

    logger.debug("No working LLM provider available — using rule-based AI monitor")
    return _rule_based_monitor(body)
