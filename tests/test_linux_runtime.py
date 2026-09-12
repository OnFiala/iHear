from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import linux  # noqa: E402
from runtime_identity import validate_runtime_identity  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops/linux"))
import install as linux_install  # noqa: E402


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
                linux,
                "ensure_private_ingress",
                side_effect=lambda *_args, **_kwargs: events.append("private_ingress"),
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
            ), patch.object(
                linux,
                "make_web_artifacts_readable",
                side_effect=lambda: events.append("web_artifact_permissions"),
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
                    "private_ingress",
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
                    "web_artifact_permissions",
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
            json.dumps({"Self": {"DNSName": "fixture-node.example-tailnet.ts.net."}}),
            "",
        )
        with patch.object(linux, "run", return_value=status) as run:
            self.assertEqual(
                linux.ensure_expected_origin(
                    {}, "https://fixture-node.example-tailnet.ts.net:8446/"
                ),
                "https://fixture-node.example-tailnet.ts.net:8446",
            )
            rejected = [
                "https://other.example-tailnet.ts.net:8446",
                "https://example.com:8446",
                "https://fixture-node.example-tailnet.ts.net:443",
            ]
            for origin in rejected:
                with self.subTest(origin=origin), self.assertRaisesRegex(RuntimeError, "Tailscale"):
                    linux.ensure_expected_origin({}, origin)
        run.assert_called_with(["tailscale", "status", "--json"], env={}, capture=True)

    def test_private_ingress_accepts_empty_prepare_and_exact_private_mappings(self) -> None:
        dns_name = "fixture-node.example-tailnet.ts.net"

        def validate(config: dict[str, object], *, require_app: bool) -> None:
            def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                payload = (
                    {"Self": {"DNSName": f"{dns_name}."}}
                    if command == ["tailscale", "status", "--json"]
                    else config
                )
                return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

            with patch.object(linux, "run", side_effect=fake_run):
                linux.ensure_private_ingress({}, require_app=require_app)

        validate({}, require_app=False)
        with self.assertRaisesRegex(RuntimeError, "mapping is missing"):
            validate({}, require_app=True)

        app = {
            "TCP": {"8446": {"HTTPS": True}},
            "Web": {
                f"{dns_name}:8446": {
                    "Handlers": {"/": {"Proxy": "http://127.0.0.1:8080"}}
                }
            },
            "AllowFunnel": {f"{dns_name}:8446": False},
        }
        validate(app, require_app=True)
        app_and_dashboard = json.loads(json.dumps(app))
        app_and_dashboard["TCP"]["9443"] = {"HTTPS": True}
        app_and_dashboard["Web"][f"{dns_name}:9443"] = {
            "Handlers": {"/": {"Proxy": "http://127.0.0.1:9080"}}
        }
        app_and_dashboard["AllowFunnel"][f"{dns_name}:9443"] = False
        validate(app_and_dashboard, require_app=True)

    def test_private_ingress_rejects_funnel_and_unexpected_mappings(self) -> None:
        dns_name = "fixture-node.example-tailnet.ts.net"
        valid = {
            "TCP": {"8446": {"HTTPS": True}},
            "Web": {
                f"{dns_name}:8446": {
                    "Handlers": {"/": {"Proxy": "http://127.0.0.1:8080"}}
                }
            },
            "AllowFunnel": {f"{dns_name}:8446": False},
        }
        invalid: list[dict[str, object]] = []
        funnel = json.loads(json.dumps(valid))
        funnel["AllowFunnel"][f"{dns_name}:8446"] = True
        invalid.append(funnel)
        unexpected_host = json.loads(json.dumps(valid))
        unexpected_host["Web"]["private-needle.invalid:8446"] = unexpected_host["Web"].pop(
            f"{dns_name}:8446"
        )
        invalid.append(unexpected_host)
        unexpected_port = json.loads(json.dumps(valid))
        unexpected_port["TCP"] = {"443": {"HTTPS": True}}
        invalid.append(unexpected_port)
        unexpected_upstream = json.loads(json.dumps(valid))
        unexpected_upstream["Web"][f"{dns_name}:8446"]["Handlers"]["/"]["Proxy"] = (
            "http://private-needle.invalid:8080"
        )
        invalid.append(unexpected_upstream)

        for config in invalid:
            def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                payload = (
                    {"Self": {"DNSName": f"{dns_name}."}}
                    if command == ["tailscale", "status", "--json"]
                    else config
                )
                return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

            with self.subTest(config=config), patch.object(linux, "run", side_effect=fake_run):
                with self.assertRaises(RuntimeError) as raised:
                    linux.ensure_private_ingress({}, require_app=True)
                self.assertNotIn("private-needle", str(raised.exception))

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

    def test_runtime_identity_accepts_owned_private_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            identity = Path(temp) / "runtime.json"
            identity.write_text('{"hostname":"fixture-current","schema_version":1}\n')
            identity.chmod(0o600)
            validate_runtime_identity(
                identity,
                expected_uid=os.getuid(),
                current_hostname="fixture-current",
            )

    def test_runtime_identity_rejects_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, "missing or unreadable"):
                validate_runtime_identity(
                    Path(temp) / "runtime.json",
                    expected_uid=os.getuid(),
                    current_hostname="fixture-current",
                )

    def test_runtime_identity_rejects_wrong_host_without_disclosure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            identity = Path(temp) / "runtime.json"
            identity.write_text('{"hostname":"fixture-private-a","schema_version":1}\n')
            identity.chmod(0o600)
            with self.assertRaises(RuntimeError) as raised:
                validate_runtime_identity(
                    identity,
                    expected_uid=os.getuid(),
                    current_hostname="fixture-private-b",
                )
            message = str(raised.exception)
            self.assertNotIn("fixture-private-a", message)
            self.assertNotIn("fixture-private-b", message)

    def test_runtime_identity_rejects_permissions_and_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            identity = Path(temp) / "runtime.json"
            identity.write_text('{"hostname":"fixture-current","schema_version":1}\n')
            identity.chmod(0o644)
            with self.assertRaisesRegex(RuntimeError, "0600"):
                validate_runtime_identity(
                    identity,
                    expected_uid=os.getuid(),
                    current_hostname="fixture-current",
                )
            identity.chmod(0o600)
            with self.assertRaisesRegex(RuntimeError, "wrong owner"):
                validate_runtime_identity(
                    identity,
                    expected_uid=os.getuid() + 1,
                    current_hostname="fixture-current",
                )

    def test_runtime_identity_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "target.json"
            identity = root / "runtime.json"
            target.write_text('{"hostname":"fixture-current","schema_version":1}\n')
            target.chmod(0o600)
            identity.symlink_to(target)
            with self.assertRaisesRegex(RuntimeError, "non-symlink"):
                validate_runtime_identity(
                    identity,
                    expected_uid=os.getuid(),
                    current_hostname="fixture-current",
                )

    def test_private_nginx_login_render_is_exact(self) -> None:
        template = (
            'if ($http_tailscale_user_login != "__IHEAR_PRIVATE_LOGIN__") '
            "{ return 403; }\n"
        )
        rendered = linux_install.render_private_nginx(
            template,
            "fixture.owner+monitor@example.invalid",
        )
        self.assertNotIn("__IHEAR_PRIVATE_LOGIN__", rendered)
        self.assertIn('"fixture.owner+monitor@example.invalid"', rendered)
        with self.assertRaisesRegex(RuntimeError, "login is invalid"):
            linux_install.render_private_nginx(template, "invalid login")
        with self.assertRaisesRegex(RuntimeError, "one quoted"):
            linux_install.render_private_nginx(template + template, "fixture@example.invalid")

    def test_web_service_uses_dedicated_account_and_confinement(self) -> None:
        service = (Path(__file__).resolve().parents[1] / "ops/linux/ihear-web.service").read_text()
        required = {
            "User=ihear-web",
            "Group=ihear-web",
            "EnvironmentFile=/home/ondrej/iHear/.env.local",
            "UnsetEnvironment=OPENAI_API_KEY",
            "WorkingDirectory=/srv/ihear-web",
            "ExecStart=/opt/ihear/node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3000",
            "ProtectHome=tmpfs",
            "ProtectSystem=strict",
            "BindReadOnlyPaths=/home/ondrej/iHear:/srv/ihear-web",
            "BindReadOnlyPaths=__IHEAR_NODE_BINARY__:/opt/ihear/node",
            "BindPaths=/var/cache/ihear-web:/srv/ihear-web/.next/cache",
            "CapabilityBoundingSet=",
            "PrivateDevices=true",
            "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
            "MemoryHigh=512M",
            "MemoryMax=768M",
            "CPUQuota=150%",
            "TasksMax=128",
        }
        self.assertTrue(required.issubset(set(service.splitlines())))
        self.assertNotIn("User=ondrej", service)
        self.assertNotIn("Group=ondrej", service)
        self.assertNotIn("SupplementaryGroups=docker", service)
        self.assertNotIn("WorkingDirectory=/home/ondrej", service)
        self.assertNotIn("ExecStart=/home/ondrej", service)
        self.assertNotIn("ReadWritePaths=/home/ondrej", service)

    def test_web_service_node_bind_is_rendered_from_canonical_path(self) -> None:
        template = "BindReadOnlyPaths=__IHEAR_NODE_BINARY__:/opt/ihear/node\n"
        rendered = linux_install.render_web_service(
            template,
            "/home/ondrej/.local/share/nodejs/bin/node",
        )
        self.assertEqual(
            rendered,
            "BindReadOnlyPaths=/home/ondrej/.local/share/nodejs/bin/node:/opt/ihear/node\n",
        )
        self.assertNotIn(linux_install.WEB_NODE_PLACEHOLDER, rendered)
        with self.assertRaisesRegex(RuntimeError, "path is invalid"):
            linux_install.render_web_service(template, "/home/ondrej/private node")

    def test_web_account_contract_rejects_groups_or_unlocked_password(self) -> None:
        account = SimpleNamespace(
            pw_name="ihear-web",
            pw_uid=430,
            pw_dir="/nonexistent",
            pw_shell="/usr/sbin/nologin",
            pw_gid=431,
        )
        group = SimpleNamespace(gr_name="ihear-web")
        with patch.object(linux_install.pwd, "getpwnam", return_value=account), patch.object(
            linux_install.grp, "getgrgid", return_value=group
        ), patch.object(linux_install.os, "getgrouplist", return_value=[431]), patch.object(
            linux_install, "run", return_value="ihear-web L 2026-09-12 0 99999 7 -1"
        ):
            linux_install.ensure_web_account()
        commands: list[tuple[str, ...]] = []

        def account_run(*argv: str) -> str:
            commands.append(argv)
            return "ihear-web L 2026-09-12 0 99999 7 -1" if argv[0] == "passwd" else ""

        with patch.object(
            linux_install.pwd,
            "getpwnam",
            side_effect=[KeyError("missing"), account],
        ), patch.object(linux_install.grp, "getgrgid", return_value=group), patch.object(
            linux_install.os, "getgrouplist", return_value=[431]
        ), patch.object(linux_install, "run", side_effect=account_run):
            linux_install.ensure_web_account()
        self.assertIn(
            (
                "useradd",
                "--system",
                "--user-group",
                "--no-create-home",
                "--home-dir",
                "/nonexistent",
                "--shell",
                "/usr/sbin/nologin",
                "ihear-web",
            ),
            commands,
        )
        with patch.object(linux_install.pwd, "getpwnam", return_value=account), patch.object(
            linux_install.grp, "getgrgid", return_value=group
        ), patch.object(linux_install.os, "getgrouplist", return_value=[431, 999]), patch.object(
            linux_install, "run", return_value="ihear-web L 2026-09-12 0 99999 7 -1"
        ):
            with self.assertRaisesRegex(RuntimeError, "no supplementary groups"):
                linux_install.ensure_web_account()
        with patch.object(linux_install.pwd, "getpwnam", return_value=account), patch.object(
            linux_install.grp, "getgrgid", return_value=group
        ), patch.object(linux_install.os, "getgrouplist", return_value=[431]), patch.object(
            linux_install, "run", return_value="ihear-web P 2026-09-12 0 99999 7 -1"
        ):
            with self.assertRaisesRegex(RuntimeError, "password must remain locked"):
                linux_install.ensure_web_account()

    def test_web_artifact_permissions_are_narrow_and_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            artifacts = root / ".next"
            nested = artifacts / "server"
            nested.mkdir(parents=True)
            output = nested / "app.js"
            output.write_text("fixture")
            external = root / "operator-secret"
            external.write_text("private")
            (artifacts / "external-link").symlink_to(external)
            artifacts.chmod(0o700)
            nested.chmod(0o700)
            output.chmod(0o600)
            external.chmod(0o600)

            linux.make_web_artifacts_readable(artifacts)
            linux.ensure_web_artifacts_readable(artifacts)
            self.assertEqual(artifacts.stat().st_mode & 0o007, 0o005)
            self.assertEqual(nested.stat().st_mode & 0o007, 0o005)
            self.assertEqual(output.stat().st_mode & 0o007, 0o004)
            self.assertEqual(external.stat().st_mode & 0o777, 0o600)
            output.chmod(0o600)
            with self.assertRaisesRegex(RuntimeError, "not readable"):
                linux.ensure_web_artifacts_readable(artifacts)

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
            linux,
            "ensure_private_ingress",
            side_effect=lambda *_args, **_kwargs: events.append("ingress"),
        ), patch.object(
            linux,
            "ensure_web_artifacts_readable",
            side_effect=lambda: events.append("artifacts"),
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
        self.assertEqual(
            events,
            [
                "origin",
                "tailscale",
                "ingress",
                "artifacts",
                "clean",
                "manifest",
                "clean",
                "foundation",
            ],
        )
        self.assertIn(
            linux.COMPOSE + ["up", "-d", "--no-build", "--pull", "never", "worker"],
            commands,
        )
        command_parts = [part for command in commands for part in command]
        self.assertNotIn("reset", command_parts)
        self.assertNotIn("build", command_parts)
        self.assertNotIn("next", command_parts)

    def test_runtime_output_and_errors_do_not_disclose_private_origin(self) -> None:
        private_origin = "https://private-needle.example-tailnet.ts.net:8446"
        failed = subprocess.CompletedProcess([], 17, "", "")
        with patch("subprocess.run", return_value=failed):
            with self.assertRaises(RuntimeError) as raised:
                linux.run(["fixture", private_origin], env={})
        self.assertNotIn("private-needle", str(raised.exception))

        def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            if command[:2] == ["docker", "info"]:
                return subprocess.CompletedProcess(command, 1, "", "")
            return subprocess.CompletedProcess(command, 0, "", "")

        output = io.StringIO()
        with patch.object(linux.local_runtime, "read_env", return_value={"APP_PUBLIC_ORIGIN": private_origin}), patch.object(
            linux, "ensure_expected_origin", return_value=private_origin
        ), patch.object(linux, "run", side_effect=fake_run), redirect_stdout(output):
            linux.status({})
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["originConfigured"])
        self.assertTrue(payload["originMatchesObservedIdentity"])
        self.assertNotIn("private-needle", output.getvalue())

        start_output = io.StringIO()
        with patch.object(linux, "existing_start_origin", return_value=private_origin), patch.object(
            linux, "ensure_expected_origin", return_value=private_origin
        ), patch.object(linux, "ensure_private_ingress"), patch.object(
            linux, "ensure_web_artifacts_readable"
        ), patch.object(
            linux, "clean_git_head", return_value="abc123"
        ), patch.object(linux, "verify_artifact_manifest"), patch.object(
            linux,
            "ensure_runtime_foundation",
            return_value={"APP_PUBLIC_ORIGIN": private_origin},
        ), patch.object(linux, "run", return_value=subprocess.CompletedProcess([], 0, "", "")), patch.object(
            linux, "ensure_worker_network"
        ), redirect_stdout(start_output):
            linux.start({})
        self.assertNotIn("private-needle", start_output.getvalue())


if __name__ == "__main__":
    unittest.main()
