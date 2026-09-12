from __future__ import annotations

import io
import base64
import hashlib
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
import domain_access  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
AUD = "a" * 16
TEAM = "https://ihear.cloudflareaccess.com"
TUNNEL = "11111111-2222-3333-4444-555555555555"
RUNTIME = {"expectedGitHead": "b" * 40, "expectedNextBuildId": "build-1",
           "expectedTunnelId": TUNNEL, "tokenSha256": "c" * 64}


class DomainAccessTests(unittest.TestCase):
    def test_binding_requires_exact_domain_origin_and_canonical_team(self) -> None:
        valid = {
            **RUNTIME,
            "schemaVersion": 1,
            "hostname": "ihear.ofops.co",
            "appOrigin": "https://ihear.ofops.co",
            "webPort": 3001,
            "nginxPort": 8081,
            "accessAud": AUD,
            "accessTeamDomain": TEAM,
        }
        binding = domain_access.validate_binding_document(valid)
        self.assertEqual(binding.access_aud, AUD)
        for key, value in (
            ("hostname", "other.ofops.co"),
            ("appOrigin", "http://ihear.ofops.co"),
            ("accessTeamDomain", TEAM + "/"),
            ("accessAud", "short"),
        ):
            rejected = dict(valid)
            rejected[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(
                domain_access.DomainAccessError, "access_binding_invalid"
            ):
                domain_access.validate_binding_document(rejected)

    def test_binding_rejects_unknown_fields_and_invalid_team_urls(self) -> None:
        document = {
            "schemaVersion": 1,
            "hostname": "ihear.ofops.co",
            "appOrigin": "https://ihear.ofops.co",
            "webPort": 3001,
            "nginxPort": 8081,
            "accessAud": AUD,
            "accessTeamDomain": TEAM,
            "unexpected": True,
        }
        with self.assertRaisesRegex(domain_access.DomainAccessError, "access_binding_invalid"):
            domain_access.validate_binding_document(document)
        for team in (
            "http://ihear.cloudflareaccess.com",
            "https://ihear.cloudflareaccess.com:443",
            "https://ihear.cloudflareaccess.com/path",
            "https://IHEAR.cloudflareaccess.com",
            "https://ihear.example.com",
            "https://ihéar.cloudflareaccess.com",
            "https://ihear.cloudflareaccess.com:bad",
        ):
            with self.subTest(team=team), self.assertRaisesRegex(
                domain_access.DomainAccessError, "access_binding_invalid"
            ):
                domain_access.validate_access_binding(AUD, team)

    def test_web_override_allows_only_fixed_public_origin(self) -> None:
        domain_access.validate_web_override("# root-owned\nAPP_PUBLIC_ORIGIN=https://ihear.ofops.co\n")
        for override in (
            "APP_PUBLIC_ORIGIN=https://private.example\n",
            "APP_PUBLIC_ORIGIN=https://ihear.ofops.co\nOPENAI_API_KEY=bad\n",
            "APP_PUBLIC_ORIGIN=https://ihear.ofops.co\nAPP_PUBLIC_ORIGIN=https://ihear.ofops.co\n",
            "NODE_ENV=production\n",
        ):
            with self.subTest(override=override), self.assertRaisesRegex(
                domain_access.DomainAccessError, "web_override_invalid"
            ):
                domain_access.validate_web_override(override)

    def test_protected_file_rejects_symlink_mode_and_owner_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protected = root / "web.env"
            protected.write_text("APP_PUBLIC_ORIGIN=https://ihear.ofops.co\n")
            protected.chmod(0o600)
            domain_access.require_regular_file(protected, mode=0o600, uid=os.getuid())
            protected.chmod(0o644)
            with self.assertRaisesRegex(domain_access.DomainAccessError, "protected_file_invalid"):
                domain_access.require_regular_file(protected, mode=0o600, uid=os.getuid())
            protected.chmod(0o600)
            link = root / "link.env"
            link.symlink_to(protected)
            with self.assertRaisesRegex(domain_access.DomainAccessError, "protected_file_invalid"):
                domain_access.require_regular_file(link, mode=0o600, uid=os.getuid())
            with self.assertRaisesRegex(domain_access.DomainAccessError, "protected_file_invalid"):
                domain_access.require_regular_file(protected, mode=0o600, uid=os.getuid() + 1)

    def test_frozen_source_requires_clean_head_and_matching_build_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".local").mkdir()
            (root / ".next").mkdir()
            manifest = root / ".local/linux-artifacts.json"
            build = root / ".next/BUILD_ID"
            manifest.write_text(json.dumps({
                "schemaVersion": 1, "gitHead": "b" * 40, "workerImageId": "sha256:fixture",
                "nextBuildId": "build-1",
            }))
            build.write_text("build-1\n")
            manifest.chmod(0o600)
            build.chmod(0o644)

            def git_result(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                output = "" if "status" in command else "b" * 40 + "\n"
                return subprocess.CompletedProcess(command, 0, output, "")

            operator = SimpleNamespace(pw_uid=os.getuid(), pw_name="ondrej")
            with patch.object(domain_access.subprocess, "run", side_effect=git_result) as runner, patch.object(
                domain_access.pwd, "getpwnam", return_value=operator
            ):
                domain_access.frozen_source_evidence(root)
                wrong_review = domain_access.RuntimeBinding(AUD, TEAM, "d" * 40,
                                                            "build-1", TUNNEL, "c" * 64)
                with self.assertRaisesRegex(domain_access.DomainAccessError, "reviewed_artifact_mismatch"):
                    domain_access.frozen_source_evidence(root, wrong_review)
                self.assertTrue(all(call.args[0][:6] == [
                    "runuser", "--user", "ondrej", "--", "git", "-C"
                ] for call in runner.call_args_list))
                manifest.write_text(json.dumps({
                    "schemaVersion": 1, "gitHead": "b" * 40, "workerImageId": "sha256:fixture",
                    "nextBuildId": "wrong",
                }))
                manifest.chmod(0o600)
                with self.assertRaisesRegex(domain_access.DomainAccessError, "artifact_identity_mismatch"):
                    domain_access.frozen_source_evidence(root)

    def test_rendered_private_config_must_match_current_owner_binding(self) -> None:
        template = (ROOT / "ops/monitor/nginx/ihear.conf.template").read_text()
        rendered = domain_access.render_private_nginx(template, "owner@example.com")
        self.assertTrue(domain_access.private_config_matches(template, rendered.encode(), "owner@example.com"))
        self.assertFalse(domain_access.private_config_matches(template, (rendered + "\n").encode(), "owner@example.com"))
        with self.assertRaisesRegex(domain_access.DomainAccessError, "private_validator_invalid"):
            domain_access.render_private_nginx(template, "bad login")

    def test_root_runtime_identity_uses_shared_validator(self) -> None:
        operator = SimpleNamespace(pw_uid=1234, pw_name="ondrej")
        with patch.object(domain_access.platform, "system", return_value="Linux"), patch.object(
            domain_access.os, "geteuid", return_value=0
        ), patch.object(domain_access.pwd, "getpwnam", return_value=operator), patch.object(
            domain_access, "validate_runtime_identity"
        ) as validator:
            domain_access.validate_root_runtime_identity(domain_access.EXPECTED_SOURCE_ROOT)
        validator.assert_called_once_with(
            domain_access.EXPECTED_SOURCE_ROOT / ".local/sandbox/runtime.json", expected_uid=1234
        )

    def test_tunnel_binary_requires_supported_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "cloudflared"
            binary.write_text("fixture")
            binary.chmod(0o755)
            completed = subprocess.CompletedProcess([str(binary), "--version"], 0, "cloudflared version 2025.4.0\n", "")
            with patch.object(domain_access, "require_regular_file") as protected, patch.object(
                domain_access.subprocess, "run", return_value=completed
            ):
                domain_access.validate_tunnel_binary(binary)
            protected.assert_called_once_with(binary, mode=0o755, uid=0)
            old = subprocess.CompletedProcess([str(binary), "--version"], 0, "cloudflared version 2025.3.9\n", "")
            with patch.object(domain_access, "require_regular_file"), patch.object(
                domain_access.subprocess, "run", return_value=old
            ), self.assertRaisesRegex(domain_access.DomainAccessError, "tunnel_binary_unsupported"):
                domain_access.validate_tunnel_binary(binary)

    def test_render_manifest_is_read_only_and_canonical(self) -> None:
        output = io.StringIO()
        with patch.object(sys, "argv", [
            "domain_access.py", "render-review-manifest", "--access-aud", AUD,
            "--access-team-domain", TEAM,
            "--git-head", "b" * 40, "--next-build-id", "build-1",
            "--tunnel-id", TUNNEL, "--token-sha256", "c" * 64,
        ]), redirect_stdout(output):
            self.assertEqual(domain_access.main(), 0)
        manifest = json.loads(output.getvalue())
        self.assertEqual(manifest["hostname"], "ihear.ofops.co")
        self.assertEqual(manifest["webPort"], 3001)
        self.assertEqual(manifest["nginxPort"], 8081)

    def test_wrong_tunnel_or_token_is_rejected_without_exposing_credential(self) -> None:
        token = base64.b64encode(json.dumps({"t": TUNNEL, "s": "synthetic-secret"}).encode())
        binding = domain_access.RuntimeBinding(AUD, TEAM, "b" * 40, "build-1", TUNNEL,
                                                hashlib.sha256(token).hexdigest())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tunnel.token"
            path.write_bytes(token)
            with patch.object(domain_access, "require_regular_file"):
                domain_access.validate_tunnel_token(path, binding)
                path.write_bytes(base64.b64encode(b'{"t":"other","s":"synthetic-secret"}'))
                with self.assertRaisesRegex(domain_access.DomainAccessError, "^tunnel_token_mismatch$"):
                    domain_access.validate_tunnel_token(path, binding)

    def test_local_status_never_claims_live_access_verified(self) -> None:
        with patch.object(domain_access, "preflight"):
            result = domain_access.safe_status(source_root=ROOT, config_root=ROOT)
        self.assertTrue(result["localPreflightReady"])
        self.assertFalse(result["liveAccessVerified"])
        self.assertNotIn("ready", result)

    def test_templates_keep_domain_boundary_and_privacy_invariants(self) -> None:
        web = (ROOT / "ops/domain/ihear-domain-web.service").read_text()
        tunnel = (ROOT / "ops/domain/ihear-domain-tunnel.service").read_text()
        nginx = (ROOT / "ops/domain/nginx.conf.template").read_text()

        self.assertIn("User=ihear-domain", web)
        self.assertIn("WorkingDirectory=/srv/ihear-domain", web)
        self.assertIn("EnvironmentFile=/home/ondrej/iHear/.env.local", web)
        self.assertIn("EnvironmentFile=/etc/ihear-domain/web.env", web)
        self.assertIn("UnsetEnvironment=OPENAI_API_KEY", web)
        self.assertIn("--port 3001", web)
        self.assertIn("CacheDirectory=ihear-domain", web)
        self.assertIn("LogNamespace=ihear-domain", web)
        self.assertIn("__IHEAR_NODE_BINARY__:/opt/ihear/node", web)

        self.assertIn("DynamicUser=yes", tunnel)
        self.assertIn("LoadCredential=tunnel.token:/etc/ihear-domain/tunnel.token", tunnel)
        self.assertIn("/opt/ihear-domain/cloudflared", tunnel)
        self.assertIn("--no-autoupdate", tunnel)
        self.assertIn("--token-file %d/tunnel.token", tunnel)
        self.assertNotIn("TUNNEL_TOKEN=", tunnel)
        self.assertNotIn("--token ", tunnel)
        for invariant in (
            "CapabilityBoundingSet=", "MemoryMax=256M", "CPUQuota=50%", "@raw-io",
            "LogNamespace=ihear-domain",
        ):
            self.assertIn(invariant, tunnel)

        log_format = nginx[nginx.index("log_format ihear_domain_privacy"):nginx.index("server {")]
        for forbidden in ("$request_uri", "$args", "$remote_addr", "$http_user_agent", "$http_cookie"):
            self.assertNotIn(forbidden, log_format)
        self.assertIn("listen 127.0.0.1:8081 default_server;", nginx)
        self.assertIn("server_name ihear.ofops.co;", nginx)
        self.assertIn("proxy_pass http://127.0.0.1:3001;", nginx)
        self.assertNotIn("127.0.0.1:3000", nginx)
        for invariant in (
            "rate=20r/s", "burst=100", "ihear_domain_connections 24", "client_max_body_size 3m",
            "proxy_set_header Host ihear.ofops.co", "proxy_set_header X-Forwarded-Proto https",
            "proxy_set_header Cf-Access-Jwt-Assertion \"\"", "proxy_set_header Tailscale-User-Login \"\"",
            "proxy_set_header X-Real-IP \"\"", "proxy_set_header Forwarded \"\"", "proxy_cache off",
            "error_log /dev/null crit",
        ):
            self.assertIn(invariant, nginx)


if __name__ == "__main__":
    unittest.main()
