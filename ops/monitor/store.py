from __future__ import annotations

import math
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY,
    collected_at INTEGER NOT NULL,
    cpu_percent REAL,
    ram_used_bytes INTEGER,
    ram_total_bytes INTEGER,
    disk_used_bytes INTEGER,
    disk_total_bytes INTEGER,
    temperature_c REAL,
    battery_percent REAL,
    ac_online INTEGER,
    lid_state TEXT,
    swap_used_bytes INTEGER,
    swap_total_bytes INTEGER,
    network_rx_bytes_per_second REAL,
    network_tx_bytes_per_second REAL,
    uptime_seconds REAL,
    host_status TEXT NOT NULL,
    docker_status TEXT NOT NULL,
    database_status TEXT NOT NULL,
    access_log_status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS samples_collected_at_idx ON samples(collected_at);

CREATE TABLE IF NOT EXISTS services (
    sample_id INTEGER NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
    service_key TEXT NOT NULL,
    service_kind TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT,
    cpu_percent REAL,
    memory_bytes INTEGER,
    PRIMARY KEY(sample_id, service_key)
);

CREATE TABLE IF NOT EXISTS app_metrics (
    sample_id INTEGER NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
    metric_key TEXT NOT NULL,
    metric_value INTEGER NOT NULL,
    PRIMARY KEY(sample_id, metric_key)
);

CREATE TABLE IF NOT EXISTS request_log (
    id INTEGER PRIMARY KEY,
    occurred_at INTEGER NOT NULL,
    request_id TEXT NOT NULL,
    method TEXT NOT NULL,
    route_class TEXT NOT NULL,
    status INTEGER NOT NULL,
    duration_ms REAL NOT NULL,
    response_bytes INTEGER NOT NULL,
    visitor_id TEXT NOT NULL,
    source_dev INTEGER NOT NULL,
    source_ino INTEGER NOT NULL,
    source_offset INTEGER NOT NULL,
    UNIQUE(source_dev, source_ino, source_offset)
);
CREATE INDEX IF NOT EXISTS request_log_occurred_at_idx ON request_log(occurred_at);
CREATE INDEX IF NOT EXISTS request_log_visitor_idx ON request_log(visitor_id, occurred_at);

CREATE TABLE IF NOT EXISTS access_cursor (
    log_path TEXT PRIMARY KEY,
    source_dev INTEGER NOT NULL,
    source_ino INTEGER NOT NULL,
    source_offset INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS collector_state (
    state_key TEXT PRIMARY KEY,
    state_value TEXT NOT NULL
);
"""


class MonitorStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def connect(self, *, readonly: bool = False) -> sqlite3.Connection:
        if readonly:
            uri = f"file:{self.path}?mode=ro"
            connection = sqlite3.connect(uri, uri=True, timeout=2)
            connection.execute("PRAGMA query_only = ON")
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=5)
            connection.executescript(SCHEMA)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 2000")
        return connection

    def record_sample(
        self,
        sample: dict[str, Any],
        services: Iterable[dict[str, Any]],
        app_metrics: dict[str, int],
    ) -> int:
        columns = (
            "collected_at", "cpu_percent", "ram_used_bytes", "ram_total_bytes",
            "disk_used_bytes", "disk_total_bytes", "temperature_c", "battery_percent",
            "ac_online", "lid_state", "swap_used_bytes", "swap_total_bytes",
            "network_rx_bytes_per_second", "network_tx_bytes_per_second",
            "uptime_seconds", "host_status", "docker_status",
            "database_status", "access_log_status",
        )
        values = [sample.get(column) for column in columns]
        with self.connect() as connection:
            cursor = connection.execute(
                f"INSERT INTO samples ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                values,
            )
            sample_id = int(cursor.lastrowid)
            connection.executemany(
                """INSERT INTO services
                   (sample_id, service_key, service_kind, status, detail, cpu_percent, memory_bytes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        sample_id, item["service_key"], item["service_kind"], item["status"],
                        item.get("detail"), item.get("cpu_percent"), item.get("memory_bytes"),
                    )
                    for item in services
                ],
            )
            connection.executemany(
                "INSERT INTO app_metrics (sample_id, metric_key, metric_value) VALUES (?, ?, ?)",
                [(sample_id, key, value) for key, value in sorted(app_metrics.items())],
            )
        return sample_id

    def prune(self, *, now: int | None = None, retention_days: int = 30) -> None:
        cutoff = (now if now is not None else int(time.time())) - retention_days * 86400
        with self.connect() as connection:
            connection.execute("DELETE FROM samples WHERE collected_at < ?", (cutoff,))
            connection.execute("DELETE FROM request_log WHERE occurred_at < ?", (cutoff,))

    def snapshot(self, *, now: int | None = None, stale_after: int = 90) -> dict[str, Any]:
        current_time = now if now is not None else int(time.time())
        with self.connect(readonly=True) as connection:
            latest_row = connection.execute(
                "SELECT * FROM samples ORDER BY collected_at DESC, id DESC LIMIT 1"
            ).fetchone()
            if latest_row is None:
                return {
                    "generatedAt": current_time,
                    "freshness": {"state": "unknown", "ageSeconds": None, "staleAfterSeconds": stale_after},
                    "latest": None,
                    "services": [],
                    "application": {},
                    "traffic": self._traffic(connection, current_time, "unknown"),
                    "history": [],
                    "requests": self._requests(connection),
                }

            latest = dict(latest_row)
            age = max(0, current_time - int(latest["collected_at"]))
            service_rows = connection.execute(
                """SELECT service_key, service_kind, status, detail, cpu_percent, memory_bytes
                   FROM services WHERE sample_id = ? ORDER BY service_kind, service_key""",
                (latest["id"],),
            ).fetchall()
            app_rows = connection.execute(
                "SELECT metric_key, metric_value FROM app_metrics WHERE sample_id = ? ORDER BY metric_key",
                (latest["id"],),
            ).fetchall()
            history_rows = connection.execute(
                """SELECT collected_at, cpu_percent, ram_used_bytes, ram_total_bytes
                   FROM samples WHERE collected_at >= ? ORDER BY collected_at""",
                (current_time - 86400,),
            ).fetchall()
            history = [dict(row) for row in history_rows]
            if len(history) > 720:
                stride = math.ceil(len(history) / 720)
                history = history[::stride]
                if history[-1]["collected_at"] != history_rows[-1]["collected_at"]:
                    history.append(dict(history_rows[-1]))
            latest.pop("id", None)
            return {
                "generatedAt": current_time,
                "freshness": {
                    "state": "fresh" if age <= stale_after else "stale",
                    "ageSeconds": age,
                    "staleAfterSeconds": stale_after,
                },
                "latest": latest,
                "services": [dict(row) for row in service_rows],
                "application": {row["metric_key"]: row["metric_value"] for row in app_rows},
                "traffic": self._traffic(connection, current_time, str(latest["access_log_status"])),
                "history": history,
                "requests": self._requests(connection),
            }

    @staticmethod
    def _traffic(connection: sqlite3.Connection, now: int, availability: str) -> dict[str, Any]:
        rows = connection.execute(
            """SELECT status, duration_ms, visitor_id FROM request_log
               WHERE occurred_at >= ? ORDER BY duration_ms""",
            (now - 86400,),
        ).fetchall()
        if not rows:
            known_empty = availability == "available"
            return {
                "availability": availability,
                "windowSeconds": 86400,
                "requests": 0 if known_empty else None,
                "errors": 0 if known_empty else None,
                "averageLatencyMs": None,
                "p95LatencyMs": None,
                "browserVisitors": 0 if known_empty else None,
            }
        durations = [float(row["duration_ms"]) for row in rows]
        p95_index = max(0, math.ceil(len(durations) * 0.95) - 1)
        return {
            "availability": availability,
            "windowSeconds": 86400,
            "requests": len(rows),
            "errors": sum(1 for row in rows if int(row["status"]) >= 500),
            "averageLatencyMs": round(sum(durations) / len(durations), 1),
            "p95LatencyMs": round(durations[p95_index], 1),
            "browserVisitors": len({row["visitor_id"] for row in rows}),
        }

    @staticmethod
    def _requests(connection: sqlite3.Connection) -> list[dict[str, Any]]:
        rows = connection.execute(
            """SELECT occurred_at, request_id, method, route_class, status,
                      duration_ms, response_bytes, visitor_id
               FROM request_log ORDER BY occurred_at DESC, id DESC LIMIT 250"""
        ).fetchall()
        return [dict(row) for row in rows]
