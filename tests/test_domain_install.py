from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "domain_install", Path(__file__).resolve().parents[1] / "ops/domain/install.py"
)
domain_install = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(domain_install)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import domain_access  # noqa: E402


class DomainInstallTests(unittest.TestCase):
    def test_exact_file_install_is_idempotent_and_refuses_different_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            self.assertTrue(
                domain_install.install_exact_bytes(
                    target, b"reviewed", mode=0o600, uid=os.getuid(), gid=os.getgid()
                )
            )
            self.assertFalse(
                domain_install.install_exact_bytes(
                    target, b"reviewed", mode=0o600, uid=os.getuid(), gid=os.getgid()
                )
            )
            with self.assertRaisesRegex(domain_install.InstallError, "target_file_conflict"):
                domain_install.install_exact_bytes(
                    target, b"different", mode=0o600, uid=os.getuid(), gid=os.getgid()
                )

    def test_exact_file_install_refuses_symlink_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "target"
            source.write_bytes(b"reviewed")
            target.symlink_to(source)
            with self.assertRaisesRegex(domain_install.InstallError, "target_file_conflict"):
                domain_install.install_exact_bytes(
                    target, b"reviewed", mode=0o600, uid=os.getuid(), gid=os.getgid()
                )

    def test_token_requires_exact_account_tunnel_and_digest_without_output(self) -> None:
        account = "a" * 32
        token = base64.b64encode(
            json.dumps({"a": account, "t": domain_install.EXPECTED_TUNNEL_ID, "s": "connector-secret"}).encode()
        )
        digest = hashlib.sha256(token).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token"
            path.write_bytes(token)
            with patch.object(domain_install, "require_regular"):
                self.assertEqual(
                    domain_install.validate_token(
                        path,
                        expected_account_id=account,
                        expected_tunnel_id=domain_install.EXPECTED_TUNNEL_ID,
                        expected_sha256=digest,
                    ),
                    token,
                )
                with self.assertRaisesRegex(domain_install.InstallError, "token_digest_invalid"):
                    domain_install.validate_token(
                        path,
                        expected_account_id=account,
                        expected_tunnel_id=domain_install.EXPECTED_TUNNEL_ID,
                        expected_sha256="b" * 64,
                    )
                with self.assertRaisesRegex(domain_install.InstallError, "token_binding_invalid"):
                    domain_install.validate_token(
                        path,
                        expected_account_id="b" * 32,
                        expected_tunnel_id=domain_install.EXPECTED_TUNNEL_ID,
                        expected_sha256=digest,
                    )

    def test_token_rejects_missing_connector_secret(self) -> None:
        account = "a" * 32
        token = base64.b64encode(json.dumps({"a": account, "t": domain_install.EXPECTED_TUNNEL_ID}).encode())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token"
            path.write_bytes(token)
            with patch.object(domain_install, "require_regular"), self.assertRaisesRegex(
                domain_install.InstallError, "token_binding_invalid"
            ):
                domain_install.validate_token(
                    path,
                    expected_account_id=account,
                    expected_tunnel_id=domain_install.EXPECTED_TUNNEL_ID,
                    expected_sha256=hashlib.sha256(token).hexdigest(),
                )

    def test_token_rejects_trailing_whitespace(self) -> None:
        account = "a" * 32
        token = base64.b64encode(
            json.dumps({"a": account, "t": domain_install.EXPECTED_TUNNEL_ID, "s": "connector-secret"}).encode()
        ) + b"\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token"
            path.write_bytes(token)
            with patch.object(domain_install, "require_regular"), self.assertRaisesRegex(
                domain_install.InstallError, "token_binding_invalid"
            ):
                domain_install.validate_token(
                    path,
                    expected_account_id=account,
                    expected_tunnel_id=domain_install.EXPECTED_TUNNEL_ID,
                    expected_sha256=hashlib.sha256(token).hexdigest(),
                )

    def test_cloudflared_digest_fails_closed_before_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "cloudflared"
            binary.write_bytes(b"not-the-reviewed-binary")
            with patch.object(domain_install, "require_regular"):
                with self.assertRaisesRegex(domain_install.InstallError, "cloudflared_digest_invalid"):
                    domain_install.install_cloudflared(binary)

    def test_staged_source_rejects_a_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.py"
            link = root / "staged.py"
            source.write_text("safe")
            link.symlink_to(source)
            with self.assertRaisesRegex(domain_install.InstallError, "required_file_invalid"):
                domain_install.read_stage_file(root, "staged.py")

    def test_stage_root_rejects_symlink_before_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target"
            staged = root / "staged"
            target.mkdir()
            staged.symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(domain_install.InstallError, "stage_directory_invalid"):
                domain_install.verified_stage_root(staged)

    def test_staged_preflight_helpers_require_frozen_hashes_before_import(self) -> None:
        with patch.object(domain_install, "stage_path", side_effect=lambda _root, relative: Path(relative)), patch.object(
            domain_install, "file_digest", return_value="0" * 64
        ):
            with self.assertRaisesRegex(domain_install.InstallError, "stage_script_digest_invalid"):
                domain_install.validate_staged_scripts(Path("/reviewed-stage"))

    def test_existing_access_log_is_preserved_without_content_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "access.jsonl"
            log.write_bytes(b'{"request_id":"existing"}\n')
            log.chmod(0o640)
            self.assertFalse(
                domain_install.ensure_access_log(log, uid=os.getuid(), gid=os.getgid())
            )
            self.assertEqual(log.read_bytes(), b'{"request_id":"existing"}\n')

    def test_domain_artifacts_bound_to_no_activation_policy(self) -> None:
        install_source = (Path(__file__).resolve().parents[1] / "ops/domain/install.py").read_text()
        logrotate = (Path(__file__).resolve().parents[1] / "ops/domain/logrotate-ihear-domain").read_text()
        journald = (Path(__file__).resolve().parents[1] / "ops/domain/journald-ihear-domain.conf").read_text()
        self.assertNotIn("systemctl start", install_source)
        self.assertNotIn("systemctl restart", install_source)
        self.assertNotIn("systemctl reload", install_source)
        self.assertNotIn("daemon-reload", install_source)
        self.assertIn("EXPECTED_RUNTIME_HEAD", install_source)
        self.assertIn("EXPECTED_RUNTIME_BUILD_ID", install_source)
        self.assertIn("EXPECTED_CLOUDFLARED_SHA256", install_source)
        self.assertIn("STAGED_SCRIPT_DIGESTS", install_source)
        self.assertIn("installed_domain_access.preflight", install_source)
        self.assertIn("maxsize 10M", logrotate)
        self.assertIn("rotate 7", logrotate)
        self.assertIn("SystemMaxUse=50M", journald)
        self.assertIn("MaxRetentionSec=7day", journald)
        self.assertIn("sharedscripts", logrotate)
        self.assertIn("/usr/sbin/nginx -s reopen", logrotate)

    def test_installer_access_binding_matches_reviewed_preflight_contract(self) -> None:
        token_digest = "d" * 64
        document = json.loads(
            domain_access.render_review_manifest(
                domain_install.ACCESS_AUD,
                domain_install.ACCESS_TEAM_DOMAIN,
                git_head=domain_install.EXPECTED_RUNTIME_HEAD,
                next_build_id=domain_install.EXPECTED_RUNTIME_BUILD_ID,
                tunnel_id=domain_install.EXPECTED_TUNNEL_ID,
                token_sha256=token_digest,
            )
        )
        self.assertEqual(document["expectedGitHead"], domain_install.EXPECTED_RUNTIME_HEAD)
        self.assertEqual(document["expectedNextBuildId"], domain_install.EXPECTED_RUNTIME_BUILD_ID)
        self.assertEqual(document["expectedTunnelId"], domain_install.EXPECTED_TUNNEL_ID)
        self.assertEqual(document["tokenSha256"], token_digest)


if __name__ == "__main__":
    unittest.main()
