"""
SQLite persistence for experiments (§5, §25). All access goes through
`ExperimentRepository`, an abstract interface — swapping to Postgres later
means writing one new class, not touching call sites (mission_api.py,
experiment_api.py, experiment_recorder.py never see SQL).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY,
    name TEXT,
    mission_id TEXT,
    started_at_ms INTEGER,
    ended_at_ms INTEGER,
    leader_id TEXT,
    follower_id TEXT,
    llm_enabled INTEGER,
    llm_provider TEXT,
    network_condition TEXT,
    git_commit TEXT,
    software_version TEXT,
    config_json TEXT,
    status TEXT DEFAULT 'RUNNING'
);

CREATE TABLE IF NOT EXISTS telemetry_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT,
    robot_id TEXT,
    timestamp_ms INTEGER,
    state_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_telemetry_exp ON telemetry_samples(experiment_id);

CREATE TABLE IF NOT EXISTS coordination_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT,
    timestamp_ms INTEGER,
    state_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_coord_exp ON coordination_samples(experiment_id);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT,
    timestamp_ms INTEGER,
    type TEXT,
    severity TEXT,
    robot_ids_json TEXT,
    message TEXT,
    value REAL,
    metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_exp ON events(experiment_id);

CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT,
    timestamp_ms INTEGER,
    recommendation_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_reco_exp ON recommendations(experiment_id);

CREATE TABLE IF NOT EXISTS role_switches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT,
    timestamp_ms INTEGER,
    previous_leader TEXT,
    previous_follower TEXT,
    new_leader TEXT,
    new_follower TEXT,
    tracking_error_before REAL,
    tracking_error_after REAL,
    stabilization_time_s REAL
);
CREATE INDEX IF NOT EXISTS idx_roleswitch_exp ON role_switches(experiment_id);
"""


class ExperimentRepository(ABC):
    @abstractmethod
    def create_experiment(self, experiment_id: str, **fields: Any) -> None: ...

    @abstractmethod
    def end_experiment(self, experiment_id: str, ended_at_ms: int, status: str) -> None: ...

    @abstractmethod
    def add_telemetry_sample(self, experiment_id: str, robot_id: str, timestamp_ms: int, state: dict) -> None: ...

    @abstractmethod
    def add_coordination_sample(self, experiment_id: str, timestamp_ms: int, state: dict) -> None: ...

    @abstractmethod
    def add_event(self, experiment_id: str, event: dict) -> None: ...

    @abstractmethod
    def add_recommendation(self, experiment_id: str, timestamp_ms: int, recommendation: dict) -> None: ...

    @abstractmethod
    def add_role_switch(self, experiment_id: str, switch: dict) -> None: ...

    @abstractmethod
    def get_experiment(self, experiment_id: str) -> Optional[dict]: ...

    @abstractmethod
    def list_experiments(self) -> list[dict]: ...

    @abstractmethod
    def get_telemetry(self, experiment_id: str, robot_id: Optional[str] = None) -> list[dict]: ...

    @abstractmethod
    def get_coordination(self, experiment_id: str) -> list[dict]: ...

    @abstractmethod
    def get_events(self, experiment_id: str) -> list[dict]: ...

    @abstractmethod
    def get_recommendations(self, experiment_id: str) -> list[dict]: ...

    @abstractmethod
    def get_role_switches(self, experiment_id: str) -> list[dict]: ...


class SQLiteExperimentRepository(ExperimentRepository):
    def __init__(self, db_path: str) -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def create_experiment(self, experiment_id: str, **fields: Any) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO experiments
                   (id, name, mission_id, started_at_ms, leader_id, follower_id,
                    llm_enabled, llm_provider, network_condition, git_commit,
                    software_version, config_json, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'RUNNING')""",
                (
                    experiment_id,
                    fields.get("name"),
                    fields.get("mission_id"),
                    fields.get("started_at_ms"),
                    fields.get("leader_id"),
                    fields.get("follower_id"),
                    int(bool(fields.get("llm_enabled"))),
                    fields.get("llm_provider"),
                    fields.get("network_condition"),
                    fields.get("git_commit"),
                    fields.get("software_version"),
                    json.dumps(fields.get("config", {})),
                ),
            )
            self._conn.commit()

    def end_experiment(self, experiment_id: str, ended_at_ms: int, status: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE experiments SET ended_at_ms = ?, status = ? WHERE id = ?",
                (ended_at_ms, status, experiment_id),
            )
            self._conn.commit()

    def add_telemetry_sample(self, experiment_id: str, robot_id: str, timestamp_ms: int, state: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO telemetry_samples (experiment_id, robot_id, timestamp_ms, state_json) VALUES (?, ?, ?, ?)",
                (experiment_id, robot_id, timestamp_ms, json.dumps(state, default=str)),
            )
            self._conn.commit()

    def add_coordination_sample(self, experiment_id: str, timestamp_ms: int, state: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO coordination_samples (experiment_id, timestamp_ms, state_json) VALUES (?, ?, ?)",
                (experiment_id, timestamp_ms, json.dumps(state, default=str)),
            )
            self._conn.commit()

    def add_event(self, experiment_id: str, event: dict) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO events
                   (experiment_id, timestamp_ms, type, severity, robot_ids_json, message, value, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    experiment_id,
                    event.get("timestamp_ms"),
                    event.get("type"),
                    event.get("severity"),
                    json.dumps(event.get("robot_ids", [])),
                    event.get("message", ""),
                    event.get("value"),
                    json.dumps(event.get("metadata", {})),
                ),
            )
            self._conn.commit()

    def add_recommendation(self, experiment_id: str, timestamp_ms: int, recommendation: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO recommendations (experiment_id, timestamp_ms, recommendation_json) VALUES (?, ?, ?)",
                (experiment_id, timestamp_ms, json.dumps(recommendation, default=str)),
            )
            self._conn.commit()

    def add_role_switch(self, experiment_id: str, switch: dict) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO role_switches
                   (experiment_id, timestamp_ms, previous_leader, previous_follower, new_leader,
                    new_follower, tracking_error_before, tracking_error_after, stabilization_time_s)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    experiment_id,
                    switch.get("timestamp_ms"),
                    switch.get("previous_leader"),
                    switch.get("previous_follower"),
                    switch.get("new_leader"),
                    switch.get("new_follower"),
                    switch.get("tracking_error_before_m"),
                    switch.get("tracking_error_after_m"),
                    switch.get("stabilization_time_s"),
                ),
            )
            self._conn.commit()

    def get_experiment(self, experiment_id: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,)).fetchone()
        return dict(row) if row else None

    def list_experiments(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM experiments ORDER BY started_at_ms DESC").fetchall()
        return [dict(r) for r in rows]

    def get_telemetry(self, experiment_id: str, robot_id: Optional[str] = None) -> list[dict]:
        with self._lock:
            if robot_id:
                rows = self._conn.execute(
                    "SELECT * FROM telemetry_samples WHERE experiment_id = ? AND robot_id = ? ORDER BY timestamp_ms",
                    (experiment_id, robot_id),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM telemetry_samples WHERE experiment_id = ? ORDER BY timestamp_ms",
                    (experiment_id,),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_coordination(self, experiment_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM coordination_samples WHERE experiment_id = ? ORDER BY timestamp_ms", (experiment_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_events(self, experiment_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE experiment_id = ? ORDER BY timestamp_ms", (experiment_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_recommendations(self, experiment_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM recommendations WHERE experiment_id = ? ORDER BY timestamp_ms", (experiment_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_role_switches(self, experiment_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM role_switches WHERE experiment_id = ? ORDER BY timestamp_ms", (experiment_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
