#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    from .store import MonitorStore
except ImportError:  # Direct execution from the installed monitor directory.
    from store import MonitorStore


DEFAULT_DB = "/var/lib/ihear-monitor/metrics.sqlite"
DEFAULT_ACCESS_LOG = "/var/log/ihear/access.jsonl"
DEFAULT_CONTAINERS = (
    "supabase_db_iHear", "supabase_kong_iHear", "supabase_storage_iHear",
    "supabase_auth_iHear", "supabase_realtime_iHear", "ihear-worker-1",
)
DEFAULT_UNITS = (
    "ihear-stack.service", "ihear-web.service", "ihear-monitor-collector.timer",
    "ihear-monitor-dashboard.service", "nginx.service", "docker.service", "tailscaled.service",
)
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.@-]{1,128}$")
HEX32 = re.compile(r"^[0-9a-f]{32}$")
METHODS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}
ROUTE_CLASSES = {
    "home", "clinic", "clinic_patient", "clinic_patient_new", "pair",
    "patient_home", "patient_pair", "patient_event", "api_session", "api_pair",
    "api_events", "api_patients", "api_report", "static_asset", "service_worker",
    "manifest", "other",
}
APP_METRIC_KEYS = (
    "events_total", "events_24h", "events_uploading", "events_queued",
    "events_analysing", "events_ready", "events_failed", "jobs_queued",
    "jobs_running", "jobs_retry", "jobs_succeeded", "jobs_failed",
    "reports_queued", "reports_generating", "reports_ready", "reports_failed",
)
AGGREGATE_SQL = """
select json_build_object(
  'events_total', (select count(*) from ihear.events),
  'events_24h', (select count(*) from ihear.events where created_at >= now() - interval '24 hours'),
  'events_uploading', (select count(*) from ihear.events where status = 'uploading'),
  'events_queued', (select count(*) from ihear.events where status = 'queued'),
  'events_analysing', (select count(*) from ihear.events where status = 'analysing'),
  'events_ready', (select count(*) from ihear.events where status = 'ready'),
  'events_failed', (select count(*) from ihear.events where status = 'failed'),
  'jobs_queued', (select count(*) from ihear.jobs where status = 'queued'),
  'jobs_running', (select count(*) from ihear.jobs where status = 'running'),
  'jobs_retry', (select count(*) from ihear.jobs where status = 'retry'),
  'jobs_succeeded', (select count(*) from ihear.jobs where status = 'succeeded'),
  'jobs_failed', (select count(*) from ihear.jobs where status = 'failed'),
  'reports_queued', (select count(*) from ihear.reports where status = 'queued'),
  'reports_generating', (select count(*) from ihear.reports where status = 'generating'),
  'reports_ready', (select count(*) from ihear.reports where status = 'ready'),
  'reports_failed', (select count(*) from ihear.reports where status = 'failed')
);
"""


def _read_text(path: str | Path) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None


def _run(command: list[str], timeout: float = 4.0) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _parse_mem_bytes(value: str) -> int | None:
    match = re.match(r"^\s*([0-9.]+)\s*([KMGTP]?i?B)\b", value)
    if not match:
        return None
    scale = {
        "B": 1, "KB": 1000, "MB": 1000**2, "GB": 1000**3,
        "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3,
        "TiB": 1024**4, "PiB": 1024**5,
    }.get(match.group(2))
    return int(float(match.group(1)) * scale) if scale else None


def collect_host(store: MonitorStore) -> dict[str, Any]:
    result: dict[str, Any] = {
        "cpu_percent": None, "ram_used_bytes": None, "ram_total_bytes": None,
        "disk_used_bytes": None, "disk_total_bytes": None, "temperature_c": None,
        "battery_percent": None, "ac_online": None, "lid_state": None,
        "swap_used_bytes": None, "swap_total_bytes": None,
        "network_rx_bytes_per_second": None, "network_tx_bytes_per_second": None,
        "uptime_seconds": None,
        "host_status": "available",
    }
    stat = _read_text("/proc/stat")
    if stat:
        fields = stat.splitlines()[0].split()
        if fields and fields[0] == "cpu" and len(fields) >= 5:
            numbers = [int(value) for value in fields[1:]]
            total, idle = sum(numbers), numbers[3] + (numbers[4] if len(numbers) > 4 else 0)
            with store.connect() as connection:
                previous = connection.execute(
                    "SELECT state_value FROM collector_state WHERE state_key = 'cpu_ticks'"
                ).fetchone()
                connection.execute(
                    """INSERT INTO collector_state(state_key, state_value) VALUES('cpu_ticks', ?)
                       ON CONFLICT(state_key) DO UPDATE SET state_value = excluded.state_value""",
                    (f"{total}:{idle}",),
                )
            if previous:
                old_total, old_idle = (int(value) for value in previous[0].split(":"))
                delta_total, delta_idle = total - old_total, idle - old_idle
                if delta_total > 0 and 0 <= delta_idle <= delta_total:
                    result["cpu_percent"] = round(100 * (1 - delta_idle / delta_total), 1)

    meminfo = _read_text("/proc/meminfo")
    if meminfo:
        parsed = {}
        for line in meminfo.splitlines():
            key, _, raw = line.partition(":")
            if raw:
                parsed[key] = int(raw.strip().split()[0]) * 1024
        total, available = parsed.get("MemTotal"), parsed.get("MemAvailable")
        if total is not None and available is not None:
            result["ram_total_bytes"] = total
            result["ram_used_bytes"] = max(0, total - available)
        swap_total, swap_free = parsed.get("SwapTotal"), parsed.get("SwapFree")
        if swap_total is not None and swap_free is not None:
            result["swap_total_bytes"] = swap_total
            result["swap_used_bytes"] = max(0, swap_total - swap_free)

    network = _read_text("/proc/net/dev")
    if network:
        received = transmitted = 0
        valid_network = False
        for line in network.splitlines()[2:]:
            if ":" not in line:
                continue
            interface, raw = line.split(":", 1)
            fields = raw.split()
            if interface.strip() == "lo" or len(fields) < 16:
                continue
            try:
                received += int(fields[0])
                transmitted += int(fields[8])
                valid_network = True
            except ValueError:
                continue
        if valid_network:
            timestamp = time.monotonic()
            with store.connect() as connection:
                previous = connection.execute(
                    "SELECT state_value FROM collector_state WHERE state_key = 'network_bytes'"
                ).fetchone()
                connection.execute(
                    """INSERT INTO collector_state(state_key, state_value) VALUES('network_bytes', ?)
                       ON CONFLICT(state_key) DO UPDATE SET state_value = excluded.state_value""",
                    (f"{received}:{transmitted}:{timestamp}",),
                )
            if previous:
                old_received, old_transmitted, old_timestamp = previous[0].split(":")
                elapsed = timestamp - float(old_timestamp)
                rx_delta, tx_delta = received - int(old_received), transmitted - int(old_transmitted)
                if elapsed > 0 and rx_delta >= 0 and tx_delta >= 0:
                    result["network_rx_bytes_per_second"] = round(rx_delta / elapsed, 1)
                    result["network_tx_bytes_per_second"] = round(tx_delta / elapsed, 1)

    try:
        disk = shutil.disk_usage("/")
        result["disk_used_bytes"], result["disk_total_bytes"] = disk.used, disk.total
    except OSError:
        pass
    uptime = _read_text("/proc/uptime")
    if uptime:
        try:
            result["uptime_seconds"] = round(float(uptime.split()[0]), 1)
        except (ValueError, IndexError):
            pass

    for path in glob.glob("/proc/acpi/button/lid/*/state"):
        raw = _read_text(path)
        if raw:
            match = re.search(r"\b(open|closed)\b", raw.lower())
            if match:
                result["lid_state"] = match.group(1)
                break

    temperatures = []
    for path in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        raw = _read_text(path)
        try:
            value = float(raw) if raw is not None else None
            if value is not None:
                value = value / 1000 if value > 200 else value
                if -20 <= value <= 150:
                    temperatures.append(value)
        except ValueError:
            continue
    if temperatures:
        result["temperature_c"] = round(max(temperatures), 1)

    for path in glob.glob("/sys/class/power_supply/*/type"):
        kind = _read_text(path)
        base = Path(path).parent
        if kind == "Battery" and result["battery_percent"] is None:
            raw = _read_text(base / "capacity")
            try:
                result["battery_percent"] = float(raw) if raw is not None else None
            except ValueError:
                pass
        if kind in {"Mains", "USB", "USB_C"} and result["ac_online"] is None:
            raw = _read_text(base / "online")
            if raw in {"0", "1"}:
                result["ac_online"] = int(raw)

    essentials = ("ram_total_bytes", "disk_total_bytes", "uptime_seconds")
    if any(result[key] is None for key in essentials):
        result["host_status"] = "partial"
    return result


def collect_containers(names: tuple[str, ...]) -> tuple[str, list[dict[str, Any]]]:
    valid = tuple(name for name in names if SAFE_NAME.fullmatch(name))
    if len(valid) != len(names):
        return "invalid_configuration", []
    services: list[dict[str, Any]] = []
    available = True
    running: dict[str, dict[str, Any]] = {}
    for name in valid:
        state_result = _run(["docker", "inspect", "--format", "{{json .State}}", name])
        if state_result is None:
            available = False
            services.append({"service_key": name, "service_kind": "container", "status": "unknown"})
            continue
        if state_result.returncode != 0:
            services.append({"service_key": name, "service_kind": "container", "status": "missing"})
            continue
        try:
            state = json.loads(state_result.stdout)
            status = str(state.get("Status") or "unknown")
            detail = "healthy" if state.get("Health", {}).get("Status") == "healthy" else None
        except (json.JSONDecodeError, AttributeError):
            status, detail, available = "unknown", None, False
        item: dict[str, Any] = {
            "service_key": name, "service_kind": "container", "status": status, "detail": detail,
            "cpu_percent": None, "memory_bytes": None,
        }
        if status == "running":
            running[name] = item
        services.append(item)

    if running:
        stats_result = _run(
            ["docker", "stats", "--no-stream", "--format", "{{json .}}", *running],
            timeout=8,
        )
        observed: set[str] = set()
        if stats_result and stats_result.returncode == 0:
            for line in stats_result.stdout.splitlines():
                try:
                    stats = json.loads(line)
                    name = str(stats.get("Name", ""))
                    if name not in running:
                        available = False
                        continue
                    running[name]["cpu_percent"] = float(str(stats.get("CPUPerc", "")).rstrip("%"))
                    running[name]["memory_bytes"] = _parse_mem_bytes(
                        str(stats.get("MemUsage", "")).split("/")[0]
                    )
                    observed.add(name)
                except (json.JSONDecodeError, ValueError, AttributeError):
                    available = False
            if observed != set(running):
                available = False
        else:
            available = False
    return ("available" if available else "partial"), services


def collect_units(names: tuple[str, ...]) -> list[dict[str, Any]]:
    services = []
    for name in names:
        if not SAFE_NAME.fullmatch(name):
            continue
        result = _run(["systemctl", "show", name, "--property=ActiveState", "--property=SubState", "--property=Result"])
        values: dict[str, str] = {}
        if result and result.returncode == 0:
            for line in result.stdout.splitlines():
                key, _, value = line.partition("=")
                values[key] = value
        detail = values.get("SubState") or None
        unit_result = values.get("Result")
        if unit_result and unit_result != "success":
            detail = f"{detail or 'unknown'} / {unit_result}"
        services.append({
            "service_key": name,
            "service_kind": "systemd",
            "status": values.get("ActiveState", "unknown"),
            "detail": detail,
        })
    return services


def collect_database(container: str) -> tuple[str, dict[str, int]]:
    if not SAFE_NAME.fullmatch(container):
        return "invalid_configuration", {}
    result = _run(
        ["docker", "exec", container, "psql", "-X", "-q", "-t", "-A", "-U", "postgres", "-d", "postgres", "-c", AGGREGATE_SQL],
        timeout=6,
    )
    if result is None or result.returncode != 0:
        return "unavailable", {}
    try:
        data = json.loads(result.stdout.strip())
        if set(data) != set(APP_METRIC_KEYS):
            return "invalid_response", {}
        metrics = {key: int(data[key]) for key in APP_METRIC_KEYS}
        if any(value < 0 for value in metrics.values()):
            raise ValueError("negative count")
        return "available", metrics
    except (json.JSONDecodeError, TypeError, ValueError):
        return "invalid_response", {}


def sanitize_log_record(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    try:
        timestamp = str(raw["timestamp"])
        occurred_at = int(time.mktime(time.strptime(timestamp[:19], "%Y-%m-%dT%H:%M:%S")))
        # Nginx emits an explicit numeric Unix timestamp too when configured; prefer it.
        if "unix_timestamp" in raw:
            occurred_at = int(float(raw["unix_timestamp"]))
        request_id = str(raw["request_id"])
        visitor = str(raw["visitor"])
        method = str(raw["method"])
        route = str(raw["route"])
        status = int(raw["status"])
        duration_ms = round(float(raw["duration_seconds"]) * 1000, 1)
        response_bytes = int(raw["bytes"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not HEX32.fullmatch(request_id) or not HEX32.fullmatch(visitor):
        return None
    if method not in METHODS or route not in ROUTE_CLASSES:
        return None
    if not 100 <= status <= 599 or not 0 <= duration_ms <= 3_600_000 or not 0 <= response_bytes <= 10**10:
        return None
    return {
        "occurred_at": occurred_at, "request_id": request_id, "method": method,
        "route_class": route, "status": status, "duration_ms": duration_ms,
        "response_bytes": response_bytes, "visitor_id": visitor,
    }


class AccessLogIngestor:
    def __init__(self, store: MonitorStore, log_path: str | Path, *, max_lines: int = 2000, max_bytes: int = 2_000_000):
        self.store = store
        self.log_path = Path(log_path)
        self.max_lines = max_lines
        self.max_bytes = max_bytes

    def ingest(self) -> str:
        try:
            current_stat = self.log_path.stat()
        except OSError:
            return "unavailable"
        with self.store.connect() as connection:
            cursor = connection.execute(
                "SELECT source_dev, source_ino, source_offset FROM access_cursor WHERE log_path = ?",
                (str(self.log_path),),
            ).fetchone()

        gap = False
        malformed = False
        if cursor is None:
            source, offset = self.log_path, 0
        elif (cursor[0], cursor[1]) == (current_stat.st_dev, current_stat.st_ino):
            source, offset = self.log_path, int(cursor[2])
            if current_stat.st_size < offset:  # copytruncate
                offset, gap = 0, True
        else:
            source = self._find_inode(int(cursor[0]), int(cursor[1]))
            offset = int(cursor[2])
            if source is None:
                source, offset, gap = self.log_path, 0, True

        remaining_lines, remaining_bytes = self.max_lines, self.max_bytes
        while remaining_lines > 0 and remaining_bytes > 0:
            records, new_offset, used_lines, used_bytes, at_end, had_malformed = self._read(
                source, offset, remaining_lines, remaining_bytes, source != self.log_path
            )
            malformed = malformed or had_malformed
            try:
                source_stat = source.stat()
            except OSError:
                return "gap"
            with self.store.connect() as connection:
                connection.executemany(
                    """INSERT OR IGNORE INTO request_log
                       (occurred_at, request_id, method, route_class, status, duration_ms,
                        response_bytes, visitor_id, source_dev, source_ino, source_offset)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        (
                            record["occurred_at"], record["request_id"], record["method"],
                            record["route_class"], record["status"], record["duration_ms"],
                            record["response_bytes"], record["visitor_id"], source_stat.st_dev,
                            source_stat.st_ino, line_offset,
                        )
                        for line_offset, record in records
                    ],
                )
                connection.execute(
                    """INSERT INTO access_cursor(log_path, source_dev, source_ino, source_offset, updated_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(log_path) DO UPDATE SET source_dev=excluded.source_dev,
                         source_ino=excluded.source_ino, source_offset=excluded.source_offset,
                         updated_at=excluded.updated_at""",
                    (str(self.log_path), source_stat.st_dev, source_stat.st_ino, new_offset, int(time.time())),
                )
            remaining_lines -= used_lines
            remaining_bytes -= used_bytes
            offset = new_offset
            if source == self.log_path or not at_end:
                break
            source, offset = self.log_path, 0
        return "gap" if gap else ("partial" if malformed else "available")

    def _find_inode(self, device: int, inode: int) -> Path | None:
        for candidate in self.log_path.parent.glob(f"{self.log_path.name}*"):
            try:
                stat = candidate.stat()
            except OSError:
                continue
            if stat.st_dev == device and stat.st_ino == inode and candidate.is_file():
                return candidate
        return None

    def _read(
        self, path: Path, offset: int, max_lines: int, max_bytes: int, rotated: bool
    ) -> tuple[list[tuple[int, dict[str, Any]]], int, int, int, bool, bool]:
        records: list[tuple[int, dict[str, Any]]] = []
        lines = used_bytes = 0
        malformed = False
        with path.open("rb") as handle:
            handle.seek(offset)
            while lines < max_lines and used_bytes < max_bytes:
                line_offset = handle.tell()
                line = handle.readline(min(max_bytes - used_bytes, 1_048_576) + 1)
                if not line:
                    break
                if not line.endswith(b"\n"):
                    if rotated or len(line) > 1_048_576:
                        # A rotated tail can never be completed. An active line beyond the
                        # hard per-line cap is malformed, not a partial write.
                        offset = handle.tell()
                        malformed = True
                    break
                offset = handle.tell()
                lines += 1
                used_bytes += len(line)
                try:
                    sanitized = sanitize_log_record(json.loads(line))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    sanitized = None
                malformed = malformed or sanitized is None
                if sanitized is not None:
                    records.append((line_offset, sanitized))
            at_end = handle.read(1) == b""
        return records, offset, lines, used_bytes, at_end, malformed


def collect_once(args: argparse.Namespace) -> None:
    store = MonitorStore(args.db)
    store.connect().close()
    access_status = AccessLogIngestor(
        store, args.access_log, max_lines=args.max_log_lines, max_bytes=args.max_log_bytes
    ).ingest()
    host = collect_host(store)
    docker_status, containers = collect_containers(tuple(args.containers))
    units = collect_units(tuple(args.units))
    database_status, app_metrics = collect_database(args.database_container)
    host.update({
        "collected_at": int(time.time()),
        "docker_status": docker_status,
        "database_status": database_status,
        "access_log_status": access_status,
    })
    store.record_sample(host, [*units, *containers], app_metrics)
    store.prune(retention_days=args.retention_days)


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Collect one bounded iHear operations sample.")
    command.add_argument("--db", default=os.environ.get("IHEAR_MONITOR_DB", DEFAULT_DB))
    command.add_argument("--access-log", default=os.environ.get("IHEAR_ACCESS_LOG", DEFAULT_ACCESS_LOG))
    command.add_argument("--retention-days", type=int, default=30)
    command.add_argument("--max-log-lines", type=int, default=2000)
    command.add_argument("--max-log-bytes", type=int, default=2_000_000)
    command.add_argument("--database-container", default=os.environ.get("IHEAR_DB_CONTAINER", "supabase_db_iHear"))
    command.add_argument("--containers", nargs="*", default=os.environ.get("IHEAR_MONITOR_CONTAINERS", ",".join(DEFAULT_CONTAINERS)).split(","))
    command.add_argument("--units", nargs="*", default=os.environ.get("IHEAR_MONITOR_UNITS", ",".join(DEFAULT_UNITS)).split(","))
    return command


if __name__ == "__main__":
    collect_once(parser().parse_args())
