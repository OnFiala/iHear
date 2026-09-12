from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import linux  # noqa: E402


class LinuxRuntimeTests(unittest.TestCase):
    def test_loopback_port_bindings_are_accepted(self) -> None:
        ports = {"8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "54321"}]}
        result = subprocess.CompletedProcess([], 0, json.dumps(ports), "")
        with patch.object(linux, "supabase_containers", return_value=[("abc", "supabase_kong_iHear")]), patch.object(
            linux, "run", return_value=result
        ):
            linux.ensure_loopback_bindings({})

    def test_public_port_binding_is_rejected(self) -> None:
        ports = {"8000/tcp": [{"HostIp": "0.0.0.0", "HostPort": "54321"}]}
        result = subprocess.CompletedProcess([], 0, json.dumps(ports), "")
        with patch.object(linux, "supabase_containers", return_value=[("abc", "supabase_kong_iHear")]), patch.object(
            linux, "run", return_value=result
        ):
            with self.assertRaisesRegex(RuntimeError, "outside loopback"):
                linux.ensure_loopback_bindings({})

    def test_docker_default_must_bind_to_loopback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "daemon.json"
            config.write_text('{"ip":"127.0.0.1"}\n')
            linux.ensure_docker_loopback_default(config)
            config.write_text('{"ip":"0.0.0.0"}\n')
            with self.assertRaisesRegex(RuntimeError, "127.0.0.1"):
                linux.ensure_docker_loopback_default(config)

    def test_dirty_checkout_is_rejected(self) -> None:
        dirty = subprocess.CompletedProcess([], 0, " M scripts/linux.py\n", "")
        with patch.object(linux, "run", return_value=dirty):
            with self.assertRaisesRegex(RuntimeError, "clean and committed"):
                linux.clean_git_head({})

    def test_fresh_prepare_creates_offline_env_before_build(self) -> None:
        events: list[str] = []
        status = subprocess.CompletedProcess(
            [],
            0,
            json.dumps(
                {
                    "DB_URL": "postgresql://example",
                    "API_URL": "http://example",
                    "SERVICE_ROLE_KEY": "test-only",
                }
            ),
            "",
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                if command == [str(linux.PNPM_BIN), "exec", "supabase", "migration", "up", "--local"]:
                    events.append("migration")
                elif command == linux.COMPOSE + ["build", "--pull=false", "worker"]:
                    env_file = root / ".env.local"
                    self.assertTrue(env_file.exists())
                    self.assertEqual(env_file.stat().st_mode & 0o777, 0o600)
                    self.assertIn("OPENAI_API_KEY=\n", env_file.read_text())
                    events.append("worker_build")
                elif command == [str(linux.PNPM_BIN), "build"]:
                    events.append("next_build")
                return subprocess.CompletedProcess(command, 0, "", "")

            def fake_supabase_start(*_: object, **__: object) -> None:
                events.append("supabase_start")

            def fake_status(*_: object, **__: object) -> subprocess.CompletedProcess[str]:
                events.append("env_status")
                return status

            with patch.object(linux, "ROOT", root), patch.object(
                linux.local_runtime, "ROOT", root
            ), patch.object(linux.local_runtime, "LOCAL", root / ".local"), patch.object(
                linux, "run", side_effect=fake_run
            ), patch.object(linux.local_runtime, "run", side_effect=fake_status), patch.object(
                linux,
                "clean_git_head",
                side_effect=lambda _: events.append("clean_head") or "abc123",
            ), patch.object(
                linux,
                "ensure_expected_origin",
                side_effect=lambda _, origin: events.append("tailscale_origin") or origin,
            ), patch.object(
                linux, "ensure_docker_loopback_default", side_effect=lambda: events.append("docker_policy")
            ), patch.object(
                linux,
                "ensure_loopback_bindings",
                side_effect=lambda *_args, **kwargs: events.append(
                    "existing_bindings" if not kwargs.get("require_containers", True) else "active_bindings"
                ),
            ), patch.object(
                linux, "ensure_supabase_network", side_effect=lambda _: events.append("network")
            ), patch.object(linux, "protected_log", side_effect=fake_supabase_start), patch.object(
                linux, "write_artifact_manifest", side_effect=lambda *_: events.append("manifest")
            ), patch(
                "builtins.print"
            ):
                linux.prepare({}, "https://ihear.test")

            values = dict(
                line.split("=", 1)
                for line in (root / ".env.local").read_text().splitlines()
                if "=" in line
            )
            self.assertEqual(values["APP_PUBLIC_ORIGIN"], "https://ihear.test")
            self.assertEqual(values["OPENAI_API_KEY"], "")
            self.assertEqual(
                events,
                [
                    "tailscale_origin",
                    "clean_head",
                    "docker_policy",
                    "existing_bindings",
                    "supabase_start",
                    "env_status",
                    "network",
                    "active_bindings",
                    "migration",
                    "worker_build",
                    "next_build",
                    "clean_head",
                    "manifest",
                ],
            )

    def test_private_origin_is_required(self) -> None:
        invalid = [
            None,
            "",
            "http://ihear.test",
            "https://localhost:3000",
            "https://127.0.0.1",
            "https://ihear.test:invalid",
        ]
        for origin in invalid:
            with self.subTest(origin=origin), self.assertRaises(RuntimeError):
                linux.validate_private_origin(origin)
        self.assertEqual(
            linux.validate_private_origin("https://ihear.private.example/"),
            "https://ihear.private.example",
        )

    def test_origin_must_match_current_tailscale_dns_and_port(self) -> None:
        status = subprocess.CompletedProcess(
            [],
            0,
            json.dumps({"Self": {"DNSName": "openclaw-appliance.example-tailnet.ts.net."}}),
            "",
        )
        with patch.object(linux, "run", return_value=status) as run:
            self.assertEqual(
                linux.ensure_expected_origin(
                    {}, "https://openclaw-appliance.example-tailnet.ts.net:8446/"
                ),
                "https://openclaw-appliance.example-tailnet.ts.net:8446",
            )
            rejected = [
                "https://other.example-tailnet.ts.net:8446",
                "https://example.com:8446",
                "https://openclaw-appliance.example-tailnet.ts.net:443",
            ]
            for origin in rejected:
                with self.subTest(origin=origin), self.assertRaisesRegex(RuntimeError, "Tailscale"):
                    linux.ensure_expected_origin({}, origin)
        run.assert_called_with(["tailscale", "status", "--json"], env={}, capture=True)

    def test_start_origin_rejects_missing_or_local_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(linux, "ROOT", root), patch.object(
                linux.local_runtime, "ROOT", root
            ):
                with self.assertRaisesRegex(RuntimeError, "missing"):
                    linux.existing_start_origin()
                env_file = root / ".env.local"
                env_file.write_text("APP_PUBLIC_ORIGIN=http://localhost:3000\n")
                env_file.chmod(0o600)
                with self.assertRaises(RuntimeError):
                    linux.existing_start_origin()

    def test_mismatched_artifact_manifest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            local = root / ".local"
            manifest = local / "linux-artifacts.json"
            (root / ".next").mkdir()
            local.mkdir()
            (root / ".next/BUILD_ID").write_text("build-current\n")
            manifest.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "gitHead": "head-old",
                        "workerImageId": "sha256:image-current",
                        "nextBuildId": "build-current",
                    }
                )
            )
            manifest.chmod(0o600)
            image = subprocess.CompletedProcess([], 0, "sha256:image-current\n", "")
            with patch.object(linux, "ROOT", root), patch.object(
                linux, "LOCAL", local
            ), patch.object(linux, "ARTIFACT_MANIFEST", manifest), patch.object(
                linux, "run", return_value=image
            ):
                with self.assertRaisesRegex(RuntimeError, "drifted"):
                    linux.verify_artifact_manifest({}, "head-current")

    def test_artifact_manifest_is_protected_and_verifiable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            local = root / ".local"
            manifest = local / "linux-artifacts.json"
            (root / ".next").mkdir()
            (root / ".next/BUILD_ID").write_text("build-current\n")
            image = subprocess.CompletedProcess([], 0, "sha256:image-current\n", "")
            with patch.object(linux, "ROOT", root), patch.object(
                linux, "LOCAL", local
            ), patch.object(linux, "ARTIFACT_MANIFEST", manifest), patch.object(
                linux, "run", return_value=image
            ):
                linux.write_artifact_manifest({}, "head-current")
                self.assertEqual(local.stat().st_mode & 0o777, 0o700)
                self.assertEqual(manifest.stat().st_mode & 0o777, 0o600)
                linux.verify_artifact_manifest({}, "head-current")

    def test_start_uses_prebuilt_worker_only(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        events: list[str] = []
        with patch.object(linux, "run", side_effect=fake_run), patch.object(
            linux, "existing_start_origin", side_effect=lambda: events.append("origin") or "https://ihear.test"
        ), patch.object(
            linux,
            "ensure_expected_origin",
            side_effect=lambda _, origin: events.append("tailscale") or origin,
        ), patch.object(
            linux, "clean_git_head", side_effect=lambda _: events.append("clean") or "abc123"
        ), patch.object(
            linux, "verify_artifact_manifest", side_effect=lambda *_: events.append("manifest")
        ), patch.object(
            linux,
            "ensure_runtime_foundation",
            side_effect=lambda *_: events.append("foundation")
            or {"APP_PUBLIC_ORIGIN": "https://ihear.test"},
        ) as foundation, patch.object(linux, "ensure_worker_network"), patch("builtins.print"):
            linux.start({})

        foundation.assert_called_once_with({}, "https://ihear.test")
        self.assertEqual(events, ["origin", "tailscale", "clean", "manifest", "clean", "foundation"])
        self.assertIn(
            linux.COMPOSE + ["up", "-d", "--no-build", "--pull", "never", "worker"],
            commands,
        )
        command_parts = [part for command in commands for part in command]
        self.assertNotIn("reset", command_parts)
        self.assertNotIn("build", command_parts)
        self.assertNotIn("next", command_parts)


if __name__ == "__main__":
    unittest.main()
