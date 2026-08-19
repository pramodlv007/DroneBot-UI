"""
Experiment Recorder (§25, §26) — records telemetry/coordination/events/
recommendations/role-switches for the active experiment and computes the
derived metrics used by the experiment dashboard and historical summaries.

rosbag2/MCAP export (§25) is left as documented future work: the recorder's
JSON export already contains every stream (telemetry, coordination,
events, recommendations, role switches) needed to synthesize a bag, but
writing one requires the rosbag2 Python API, which — like everything else
ROS2 — is unavailable in this authoring environment (see docs/audit.md's
decision log). The JSON/CSV export is the supported format today; see
docs/experiments.md for the rosbag2 conversion path.
"""

from __future__ import annotations

import csv
import io
import statistics
import subprocess
from dataclasses import dataclass
from typing import Optional

from app.db import ExperimentRepository
from app.models import CoordinationState, MissionEvent, RobotState, SupervisorRecommendation, now_ms


def _git_commit() -> Optional[str]:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


@dataclass
class ExperimentMetrics:
    tracking_rmse_m: Optional[float]
    mean_tracking_error_m: Optional[float]
    max_tracking_error_m: Optional[float]
    p95_tracking_error_m: Optional[float]
    mean_separation_m: Optional[float]
    max_separation_m: Optional[float]
    mean_latency_ms: Optional[float]
    max_latency_ms: Optional[float]
    mission_duration_s: Optional[float]
    warning_count: int
    critical_event_count: int
    role_switch_count: int
    mean_stabilization_time_s: Optional[float]
    llm_recommendation_count: int
    mean_llm_latency_ms: Optional[float]


class ExperimentRecorder:
    def __init__(self, repository: ExperimentRepository) -> None:
        self._repo = repository
        self._active_experiment_id: Optional[str] = None

    @property
    def active_experiment_id(self) -> Optional[str]:
        return self._active_experiment_id

    def start(
        self,
        experiment_id: str,
        name: str,
        mission_id: str,
        leader_id: Optional[str],
        follower_id: Optional[str],
        llm_enabled: bool,
        llm_provider: str,
        config: dict,
    ) -> None:
        self._repo.create_experiment(
            experiment_id,
            name=name,
            mission_id=mission_id,
            started_at_ms=now_ms(),
            leader_id=leader_id,
            follower_id=follower_id,
            llm_enabled=llm_enabled,
            llm_provider=llm_provider,
            git_commit=_git_commit(),
            software_version="0.2.0",
            config=config,
        )
        self._active_experiment_id = experiment_id

    def stop(self, status: str = "COMPLETED") -> None:
        if self._active_experiment_id:
            self._repo.end_experiment(self._active_experiment_id, now_ms(), status)
        self._active_experiment_id = None

    def record_telemetry(self, state: RobotState) -> None:
        if not self._active_experiment_id:
            return
        self._repo.add_telemetry_sample(
            self._active_experiment_id, state.robot_id, state.received_timestamp_ms, state.model_dump(mode="json")
        )

    def record_coordination(self, state: CoordinationState) -> None:
        if not self._active_experiment_id:
            return
        self._repo.add_coordination_sample(self._active_experiment_id, state.updated_at_ms, state.model_dump(mode="json"))

    def record_event(self, event: MissionEvent) -> None:
        if not self._active_experiment_id:
            return
        self._repo.add_event(self._active_experiment_id, event.model_dump(mode="json"))

    def record_recommendation(self, recommendation: SupervisorRecommendation) -> None:
        if not self._active_experiment_id:
            return
        self._repo.add_recommendation(
            self._active_experiment_id, recommendation.timestamp_ms, recommendation.model_dump(mode="json")
        )

    def record_role_switch(self, switch: dict) -> None:
        if not self._active_experiment_id:
            return
        self._repo.add_role_switch(self._active_experiment_id, switch)

    # -- metrics -----------------------------------------------------------

    def compute_metrics(self, experiment_id: str) -> ExperimentMetrics:
        experiment = self._repo.get_experiment(experiment_id)
        coordination_rows = self._repo.get_coordination(experiment_id)
        events = self._repo.get_events(experiment_id)
        recommendations = self._repo.get_recommendations(experiment_id)
        role_switches = self._repo.get_role_switches(experiment_id)

        import json as _json

        tracking_errors = []
        separations = []
        latencies = []
        for row in coordination_rows:
            state = _json.loads(row["state_json"])
            if state.get("tracking_error_m") is not None:
                tracking_errors.append(state["tracking_error_m"])
            if state.get("separation_m") is not None:
                separations.append(state["separation_m"])
            if state.get("telemetry_latency_ms") is not None:
                latencies.append(state["telemetry_latency_ms"])

        duration_s = None
        if experiment and experiment.get("started_at_ms") and experiment.get("ended_at_ms"):
            duration_s = (experiment["ended_at_ms"] - experiment["started_at_ms"]) / 1000.0

        stabilization_times = [
            r["stabilization_time_s"] for r in role_switches if r.get("stabilization_time_s") is not None
        ]
        llm_latencies = []
        for r in recommendations:
            rec = _json.loads(r["recommendation_json"])
            if rec.get("latency_ms") is not None:
                llm_latencies.append(rec["latency_ms"])

        return ExperimentMetrics(
            tracking_rmse_m=_rmse(tracking_errors),
            mean_tracking_error_m=_mean(tracking_errors),
            max_tracking_error_m=max(tracking_errors) if tracking_errors else None,
            p95_tracking_error_m=_percentile(tracking_errors, 95),
            mean_separation_m=_mean(separations),
            max_separation_m=max(separations) if separations else None,
            mean_latency_ms=_mean(latencies),
            max_latency_ms=max(latencies) if latencies else None,
            mission_duration_s=duration_s,
            warning_count=sum(1 for e in events if e.get("severity") == "WARNING"),
            critical_event_count=sum(1 for e in events if e.get("severity") == "CRITICAL"),
            role_switch_count=len(role_switches),
            mean_stabilization_time_s=_mean(stabilization_times),
            llm_recommendation_count=len(recommendations),
            mean_llm_latency_ms=_mean(llm_latencies),
        )

    # -- export --------------------------------------------------------

    def export_json(self, experiment_id: str) -> dict:
        return {
            "experiment": self._repo.get_experiment(experiment_id),
            "telemetry": self._repo.get_telemetry(experiment_id),
            "coordination": self._repo.get_coordination(experiment_id),
            "events": self._repo.get_events(experiment_id),
            "recommendations": self._repo.get_recommendations(experiment_id),
            "role_switches": self._repo.get_role_switches(experiment_id),
            "metrics": self.compute_metrics(experiment_id).__dict__,
        }

    def export_csv(self, experiment_id: str) -> str:
        """Flat CSV of the coordination time series — the single stream
        most useful for quick plotting/spreadsheet analysis. Full
        multi-stream data is available via export_json."""
        rows = self._repo.get_coordination(experiment_id)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["timestamp_ms", "tracking_error_m", "separation_m", "heading_error_deg", "telemetry_latency_ms", "state"])
        import json as _json

        for row in rows:
            state = _json.loads(row["state_json"])
            writer.writerow(
                [
                    row["timestamp_ms"],
                    state.get("tracking_error_m"),
                    state.get("separation_m"),
                    state.get("heading_error_deg"),
                    state.get("telemetry_latency_ms"),
                    state.get("state"),
                ]
            )
        return buf.getvalue()


def _mean(values: list[float]) -> Optional[float]:
    return statistics.mean(values) if values else None


def _rmse(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return (sum(v * v for v in values) / len(values)) ** 0.5


def _percentile(values: list[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(ordered) - 1)
    if f == c:
        return ordered[f]
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)
