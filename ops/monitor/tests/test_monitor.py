from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from collector import AccessLogIngestor, collect_containers, collect_host, sanitize_log_record  # noqa: E402
from server import DashboardApp, HTML, safe_json_bytes  # noqa: E402
from store import MonitorStore  # noqa: E402


LOGIN = "owner@example.ts.net"
RID = "a" * 32
VISITOR = "b" * 32


def record(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "timestamp": "2026-09-12T12:00:00+02:00",
        "unix_timestamp": 1789214400.0,
        "request_id": RID,
        "method": "GET",
        "route": "pair",
        "status": 200,
        "duration_seconds": 0.125,
        "bytes": 512,
        "visitor": VISITOR,
    }
    value.update(overrides)
    return value


class MonitorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "metrics.sqlite"
        self.log = self.root / "access.jsonl"
        self.store = MonitorStore(self.db)
        self.store.connect().close()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def app(self) -> DashboardApp:
        return DashboardApp(self.store, LOGIN, stale_after=90)

    def test_dashboard_auth_fails_closed_when_header_missing_or_wrong(self) -> None:
        for headers in ({}, {"Tailscale-User-Login": "attacker@example.ts.net"}):
            status, _, body = self.app().respond("GET", "/", headers)
            self.assertEqual(status, 403)
            self.assertEqual(json.loads(body), {"error": "forbidden"})

    def test_dashboard_requires_configured_exact_login(self) -> None:
        with self.assertRaises(ValueError):
            DashboardApp(self.store, "")
        with self.assertRaises(ValueError):
            DashboardApp(self.store, f" {LOGIN}")

    def test_dashboard_auth_covers_api_and_correct_header_succeeds(self) -> None:
        forbidden, _, _ = self.app().respond("GET", "/api/snapshot", {})
        allowed, content_type, _ = self.app().respond(
            "GET", "/api/snapshot", {"Tailscale-User-Login": LOGIN}
        )
        self.assertEqual(forbidden, 403)
        self.assertEqual(allowed, 200)
        self.assertEqual(content_type, "application/json")

    def test_safe_json_and_dashboard_dom_resist_markup_injection(self) -> None:
        encoded = safe_json_bytes({"value": "</script><img src=x onerror=alert(1)>&"})
        self.assertNotIn(b"<", encoded)
        self.assertNotIn(b">", encoded)
        self.assertNotIn(b"&", encoded)
        self.assertNotIn("innerHTML", HTML)
        self.assertIn("textContent", HTML)

    def test_log_contract_rejects_raw_path_pairing_code_and_extra_method(self) -> None:
        secret = "PAIR-CODE-7ZQ9"
        self.assertIsNone(sanitize_log_record(record(route=f"/pair/{secret}")))
        self.assertIsNone(sanitize_log_record(record(route="pair", method="TRACE")))
        self.assertNotIn(secret, json.dumps(sanitize_log_record(record())))

    def test_nginx_log_format_never_emits_raw_path_query_or_sensitive_fields(self) -> None:
        config = (ROOT / "nginx" / "ihear.conf.template").read_text()
        log_format = config[config.index("log_format ihear_privacy"):config.index("server {")]
        for forbidden in ("$request_uri", "$args", "$remote_addr", "$http_user_agent", "$http_cookie"):
            self.assertNotIn(forbidden, log_format)
        self.assertIn('"route":"$ihear_route_class"', log_format)

    def test_access_log_replay_is_exactly_once(self) -> None:
        self.log.write_text(json.dumps(record()) + "\n")
        ingestor = AccessLogIngestor(self.store, self.log)
        self.assertEqual(ingestor.ingest(), "available")
        self.assertEqual(ingestor.ingest(), "available")
        with self.store.connect() as connection:
            count = connection.execute("SELECT count(*) FROM request_log").fetchone()[0]
        self.assertEqual(count, 1)

    def test_partial_line_is_not_advanced_and_is_ingested_after_completion(self) -> None:
        serialized = json.dumps(record())
        self.log.write_text(serialized[:-5])
        ingestor = AccessLogIngestor(self.store, self.log)
        ingestor.ingest()
        with self.store.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM request_log").fetchone()[0], 0)
        with self.log.open("a") as handle:
            handle.write(serialized[-5:] + "\n")
        ingestor.ingest()
        with self.store.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM request_log").fetchone()[0], 1)

    def test_rename_rotation_drains_old_inode_then_new_file_without_duplicates(self) -> None:
        first, second = record(request_id="1" * 32), record(request_id="2" * 32)
        self.log.write_text(json.dumps(first) + "\n")
        ingestor = AccessLogIngestor(self.store, self.log)
        ingestor.ingest()
        rotated = self.root / "access.jsonl.1"
        os.rename(self.log, rotated)
        with rotated.open("a") as handle:
            handle.write(json.dumps(record(request_id="3" * 32)) + "\n")
        self.log.write_text(json.dumps(second) + "\n")
        ingestor.ingest()
        ingestor.ingest()
        with self.store.connect() as connection:
            ids = [row[0] for row in connection.execute("SELECT request_id FROM request_log ORDER BY id")]
        self.assertEqual(ids, ["1" * 32, "3" * 32, "2" * 32])

    def test_malformed_and_oversized_values_are_skipped_without_stopping_cursor(self) -> None:
        self.log.write_text("not-json\n" + json.dumps(record(status=999)) + "\n" + json.dumps(record()) + "\n")
        self.assertEqual(AccessLogIngestor(self.store, self.log).ingest(), "partial")
        with self.store.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM request_log").fetchone()[0], 1)

    def test_overlong_line_is_dropped_and_does_not_pin_cursor(self) -> None:
        self.log.write_bytes(b"{" + b"x" * 1_048_576)
        ingestor = AccessLogIngestor(self.store, self.log, max_bytes=2_000_000)
        self.assertEqual(ingestor.ingest(), "partial")
        with self.log.open("ab") as handle:
            handle.write(b"\n" + json.dumps(record()).encode() + b"\n")
        self.assertEqual(ingestor.ingest(), "partial")
        self.assertEqual(ingestor.ingest(), "available")
        with self.store.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM request_log").fetchone()[0], 1)

    def test_unknown_and_stale_are_distinct_from_zero(self) -> None:
        empty = self.store.snapshot(now=1000, stale_after=90)
        self.assertEqual(empty["freshness"]["state"], "unknown")
        self.assertIsNone(empty["latest"])
        self.store.record_sample(
            {
                "collected_at": 800, "cpu_percent": None, "ram_used_bytes": None,
                "ram_total_bytes": None, "disk_used_bytes": 0, "disk_total_bytes": 100,
                "temperature_c": None, "battery_percent": None, "ac_online": None,
                "lid_state": None, "swap_used_bytes": None, "swap_total_bytes": None,
                "network_rx_bytes_per_second": None, "network_tx_bytes_per_second": None,
                "uptime_seconds": None, "host_status": "partial", "docker_status": "unavailable",
                "database_status": "unavailable", "access_log_status": "unavailable",
            }, [], {},
        )
        stale = self.store.snapshot(now=1000, stale_after=90)
        self.assertEqual(stale["freshness"]["state"], "stale")
        self.assertIsNone(stale["latest"]["cpu_percent"])
        self.assertEqual(stale["latest"]["disk_used_bytes"], 0)
        self.assertEqual(stale["traffic"]["availability"], "unavailable")
        self.assertIsNone(stale["traffic"]["requests"])
        self.assertIsNone(stale["traffic"]["browserVisitors"])

    def test_linux_host_probe_reads_cpu_memory_swap_network_power_and_lid(self) -> None:
        calls = {"stat": 0, "network": 0}

        def fake_read(path: object) -> str | None:
            value = str(path)
            if value == "/proc/stat":
                calls["stat"] += 1
                return "cpu  100 0 100 800 0\n" if calls["stat"] == 1 else "cpu  150 0 150 900 0\n"
            if value == "/proc/meminfo":
                return "MemTotal: 8000000 kB\nMemAvailable: 3000000 kB\nSwapTotal: 2000000 kB\nSwapFree: 1500000 kB\n"
            if value == "/proc/net/dev":
                calls["network"] += 1
                received, transmitted = ((1000, 2000) if calls["network"] == 1 else (3000, 5000))
                return f"head\nhead\neth0: {received} 0 0 0 0 0 0 0 {transmitted} 0 0 0 0 0 0 0\n"
            if value == "/proc/uptime":
                return "7200.0 1000.0"
            if value.endswith("/lid/LID/state"):
                return "state: closed"
            if value.endswith("/BAT0/type"):
                return "Battery"
            if value.endswith("/BAT0/capacity"):
                return "84"
            if value.endswith("/AC/type"):
                return "Mains"
            if value.endswith("/AC/online"):
                return "1"
            return None

        def fake_glob(pattern: str) -> list[str]:
            if "button/lid" in pattern:
                return ["/proc/acpi/button/lid/LID/state"]
            if "power_supply" in pattern:
                return ["/sys/class/power_supply/BAT0/type", "/sys/class/power_supply/AC/type"]
            return []

        with patch("collector._read_text", side_effect=fake_read), \
             patch("collector.glob.glob", side_effect=fake_glob), \
             patch("collector.time.monotonic", side_effect=[100.0, 102.0]), \
             patch("collector.shutil.disk_usage", return_value=type("Usage", (), {"total": 1000, "used": 400})()):
            collect_host(self.store)
            result = collect_host(self.store)
        self.assertEqual(result["cpu_percent"], 50.0)
        self.assertEqual(result["ram_used_bytes"], 5_000_000 * 1024)
        self.assertEqual(result["swap_used_bytes"], 500_000 * 1024)
        self.assertEqual(result["network_rx_bytes_per_second"], 1000.0)
        self.assertEqual(result["network_tx_bytes_per_second"], 1500.0)
        self.assertEqual(result["battery_percent"], 84.0)
        self.assertEqual(result["ac_online"], 1)
        self.assertEqual(result["lid_state"], "closed")

    def test_container_stats_are_batched_once_and_matched_by_name(self) -> None:
        calls: list[tuple[list[str], float]] = []

        def fake_run(command: list[str], timeout: float = 4.0):
            calls.append((command, timeout))
            if command[1] == "inspect":
                name = command[-1]
                payload = {"Status": "running", "Health": {"Status": "healthy"}}
                return type("Result", (), {"returncode": 0, "stdout": json.dumps(payload)})()
            payload = "\n".join((
                json.dumps({"Name": "db", "CPUPerc": "1.25%", "MemUsage": "128MiB / 1GiB"}),
                json.dumps({"Name": "worker", "CPUPerc": "12.5%", "MemUsage": "1.5GiB / 2GiB"}),
            ))
            return type("Result", (), {"returncode": 0, "stdout": payload})()

        with patch("collector._run", side_effect=fake_run):
            status, services = collect_containers(("db", "worker"))
        stats_calls = [(command, timeout) for command, timeout in calls if command[1] == "stats"]
        self.assertEqual(len(stats_calls), 1)
        self.assertEqual(stats_calls[0][0][-2:], ["db", "worker"])
        self.assertEqual(stats_calls[0][1], 8)
        self.assertEqual(status, "available")
        by_name = {item["service_key"]: item for item in services}
        self.assertEqual(by_name["db"]["memory_bytes"], 128 * 1024 * 1024)
        self.assertEqual(by_name["worker"]["cpu_percent"], 12.5)

    def test_missing_batched_stats_row_is_explicitly_partial(self) -> None:
        def fake_run(command: list[str], timeout: float = 4.0):
            if command[1] == "inspect":
                return type("Result", (), {"returncode": 0, "stdout": '{"Status":"running"}'})()
            return type("Result", (), {
                "returncode": 0,
                "stdout": '{"Name":"db","CPUPerc":"1%","MemUsage":"1MiB / 1GiB"}',
            })()

        with patch("collector._run", side_effect=fake_run):
            status, services = collect_containers(("db", "worker"))
        self.assertEqual(status, "partial")
        worker = next(item for item in services if item["service_key"] == "worker")
        self.assertIsNone(worker["cpu_percent"])
        self.assertIsNone(worker["memory_bytes"])

    def test_history_is_retained_for_30_days_and_old_requests_are_pruned(self) -> None:
        now = 4_000_000
        for timestamp in (now - 31 * 86400, now - 30 * 86400 + 1, now):
            self.store.record_sample(
                {
                    "collected_at": timestamp, "host_status": "available", "docker_status": "available",
                    "database_status": "available", "access_log_status": "available",
                }, [], {},
            )
        with self.store.connect() as connection:
            connection.execute(
                """INSERT INTO request_log(occurred_at,request_id,method,route_class,status,duration_ms,
                   response_bytes,visitor_id,source_dev,source_ino,source_offset)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (now - 31 * 86400, RID, "GET", "home", 200, 1.0, 1, VISITOR, 1, 1, 0),
            )
        self.store.prune(now=now, retention_days=30)
        with self.store.connect() as connection:
            samples = connection.execute("SELECT collected_at FROM samples ORDER BY collected_at").fetchall()
            requests = connection.execute("SELECT count(*) FROM request_log").fetchone()[0]
        self.assertEqual([row[0] for row in samples], [now - 30 * 86400 + 1, now])
        self.assertEqual(requests, 0)


if __name__ == "__main__":
    unittest.main()
