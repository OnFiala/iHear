#!/usr/bin/env python3
"""Install reviewed iHear domain-route artifacts without activating them.

This is deliberately a root-only, idempotent installer for the verified Linux
runtime. It neither reloads nor starts services, contacts Cloudflare, alters the
private ingress, or prints tokens, identifiers, or private network bindings.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import grp
import re
import stat
import subprocess
import sys
from types import ModuleType


RUNTIME_ROOT = Path("/home/ondrej/iHear")
EXPECTED_RUNTIME_HEAD = "f3ab5a6fc5813f845ca44eef28f5e621eab907e3"
EXPECTED_RUNTIME_BUILD_ID = "leIR2dbOQwxwEI6VTkMTE"
EXPECTED_TUNNEL_ID = "29887da3-bdea-4a87-a3b1-b27259261419"
DEFAULT_STAGE_ROOT = Path("/opt/ihear-domain/candidate")
DOMAIN_ROOT = Path("/opt/ihear-domain")
DOMAIN_CONFIG = Path("/etc/ihear-domain")
DOMAIN_LOG = Path("/var/log/ihear-domain")
DOMAIN_WEB_USER = "ihear-domain"
EXPECTED_CLOUDFLARED_SHA256 = "03f1f25d1cc93b9ad6c60569d44060bc4f17ed97075760ed8cfca4b12dcd68cc"
ACCESS_AUD = "32ee10ef4535aec531f83687b213fde79865b42f7dba718353bd9066b33cf8f8"
ACCESS_TEAM_DOMAIN = "https://fancy-bird-04b3.cloudflareaccess.com"
STAGED_SCRIPT_DIGESTS = {
    "scripts/domain_access.py": "fff55873c2f307172c38a616638c4ac9e1e8d51be1aadab702ecc44c3d99b807",
    "scripts/runtime_identity.py": "729df515d17ec2b89ce47de8e049fe8b451105c9a34bab53581d7f27060a399c",
}


class InstallError(RuntimeError):
    """A safe, non-sensitive reason why the installer stopped."""


def fail(message: str) -> None:
    raise InstallError(message)


def require_root() -> None:
    if os.geteuid() != 0:
        fail("root_required")


def require_regular(path: Path, *, mode: int | None = None, uid: int | None = None) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise InstallError("required_file_missing") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        fail("required_file_invalid")
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        fail("required_file_invalid")
    if mode is not None and stat.S_IMODE(metadata.st_mode) != mode:
        fail("required_file_invalid")
    if uid is not None and metadata.st_uid != uid:
        fail("required_file_invalid")
    return metadata


def require_directory(path: Path, *, mode: int, uid: int, gid: int) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        path.mkdir(mode=mode, parents=True)
        os.chown(path, uid, gid)
        path.chmod(mode)
        return
    except OSError as error:
        raise InstallError("target_directory_unavailable") from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != mode
        or metadata.st_uid != uid
        or metadata.st_gid != gid
    ):
        fail("target_directory_conflict")


def require_staged_directory(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise InstallError("stage_directory_missing") from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or metadata.st_uid != 0
        or metadata.st_gid != 0
    ):
        fail("stage_directory_invalid")


def install_exact_bytes(path: Path, content: bytes, *, mode: int, uid: int, gid: int) -> bool:
    """Create once, or accept only an exact safe already-installed file."""
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags, mode)
        try:
            os.fchown(descriptor, uid, gid)
            os.fchmod(descriptor, mode)
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(content)
        finally:
            os.close(descriptor)
        return True
    except OSError as error:
        raise InstallError("target_file_unavailable") from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != mode
        or metadata.st_uid != uid
        or metadata.st_gid != gid
    ):
        fail("target_file_conflict")
    try:
        existing = path.read_bytes()
    except OSError as error:
        raise InstallError("target_file_unavailable") from error
    if existing != content:
        fail("target_file_conflict")
    return False


def read_stage_file(stage_root: Path, relative: str) -> bytes:
    path = stage_path(stage_root, relative)
    require_regular(path, uid=0)
    try:
        return path.read_bytes()
    except OSError as error:
        raise InstallError("stage_file_unavailable") from error


def stage_path(stage_root: Path, relative: str) -> Path:
    current = stage_root
    for part in Path(relative).parts[:-1]:
        current = current / part
        try:
            metadata = current.lstat()
        except OSError as error:
            raise InstallError("stage_file_unavailable") from error
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            fail("stage_file_invalid")
    return stage_root / relative


def load_module(path: Path, name: str, *, uid: int) -> ModuleType:
    require_regular(path, uid=uid)
    module_spec = importlib.util.spec_from_file_location(name, path)
    if module_spec is None or module_spec.loader is None:
        fail("stage_module_invalid")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[name] = module
    try:
        module_spec.loader.exec_module(module)
    except Exception as error:  # staged source is untrusted until it imports cleanly
        raise InstallError("stage_module_invalid") from error
    return module


def validate_staged_scripts(stage_root: Path) -> None:
    """Pin both preflight helpers before importing any staged Python source."""
    for relative, expected_digest in STAGED_SCRIPT_DIGESTS.items():
        if file_digest(stage_path(stage_root, relative)) != expected_digest:
            fail("stage_script_digest_invalid")


def validate_runtime(stage_root: Path, source_root: Path, expected_head: str) -> tuple[ModuleType, ModuleType]:
    if source_root.resolve() != RUNTIME_ROOT.resolve():
        fail("source_root_invalid")
    validate_staged_scripts(stage_root)
    runtime_identity = load_module(
        stage_path(stage_root, "scripts/runtime_identity.py"), "ihear_domain_runtime_identity", uid=0
    )
    sys.modules["runtime_identity"] = runtime_identity
    domain_access = load_module(
        stage_path(stage_root, "scripts/domain_access.py"), "ihear_domain_access", uid=0
    )
    try:
        domain_access.validate_root_runtime_identity(source_root)
        domain_access.frozen_source_evidence(source_root)
        domain_access.validate_private_validator(source_root)
    except Exception as error:
        raise InstallError("runtime_preflight_failed") from error
    operator = pwd.getpwnam("ondrej")
    result = subprocess.run(
        ["runuser", "--user", operator.pw_name, "--", "git", "-C", str(source_root), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or result.stdout.strip() != expected_head:
        fail("runtime_head_mismatch")
    try:
        build_id = (source_root / ".next/BUILD_ID").read_text(encoding="utf-8").strip()
    except OSError as error:
        raise InstallError("runtime_build_unavailable") from error
    if build_id != EXPECTED_RUNTIME_BUILD_ID:
        fail("runtime_build_mismatch")
    return runtime_identity, domain_access


def validate_token(
    token_path: Path, *, expected_account_id: str, expected_tunnel_id: str, expected_sha256: str
) -> bytes:
    require_regular(token_path, mode=0o400, uid=0)
    if not re.fullmatch(r"[0-9a-f]{32}", expected_account_id) or not re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", expected_tunnel_id
    ) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256) or expected_tunnel_id != EXPECTED_TUNNEL_ID:
        fail("token_binding_invalid")
    try:
        token = token_path.read_bytes()
        if not token or token != token.strip():
            fail("token_binding_invalid")
        payload = json.loads(base64.b64decode(token, validate=True))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, OSError) as error:
        raise InstallError("token_binding_invalid") from error
    if (
        not isinstance(payload, dict)
        or payload.get("a") != expected_account_id
        or payload.get("t") != expected_tunnel_id
        or not isinstance(payload.get("s"), str)
        or not payload["s"]
    ):
        fail("token_binding_invalid")
    if hashlib.sha256(token).hexdigest() != expected_sha256:
        fail("token_digest_invalid")
    return token


def file_digest(path: Path) -> str:
    require_regular(path, uid=0)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def install_cloudflared(source: Path) -> bool:
    if file_digest(source) != EXPECTED_CLOUDFLARED_SHA256:
        fail("cloudflared_digest_invalid")
    destination = DOMAIN_ROOT / "cloudflared"
    if destination.exists() or destination.is_symlink():
        require_regular(destination, mode=0o755, uid=0)
        if file_digest(destination) != EXPECTED_CLOUDFLARED_SHA256:
            fail("cloudflared_target_conflict")
        return False
    return install_exact_bytes(destination, source.read_bytes(), mode=0o755, uid=0, gid=0)


def ensure_domain_account() -> None:
    try:
        account = pwd.getpwnam(DOMAIN_WEB_USER)
    except KeyError:
        subprocess.run(
            ["useradd", "--system", "--user-group", "--no-create-home", "--home-dir", "/nonexistent",
             "--shell", "/usr/sbin/nologin", DOMAIN_WEB_USER],
            check=True,
        )
        account = pwd.getpwnam(DOMAIN_WEB_USER)
    try:
        group = grp.getgrgid(account.pw_gid)
        groups = set(os.getgrouplist(DOMAIN_WEB_USER, account.pw_gid))
    except (KeyError, OSError) as error:
        raise InstallError("domain_account_invalid") from error
    if (
        account.pw_uid <= 0 or account.pw_uid >= 1000 or account.pw_dir != "/nonexistent"
        or account.pw_shell != "/usr/sbin/nologin" or group.gr_name != DOMAIN_WEB_USER
        or groups != {account.pw_gid}
    ):
        fail("domain_account_invalid")
    state = subprocess.run(["passwd", "-S", DOMAIN_WEB_USER], text=True, capture_output=True, check=False)
    if state.returncode != 0 or len(state.stdout.split()) < 2 or state.stdout.split()[1] != "L":
        fail("domain_account_invalid")


def render_web_service(template: bytes, node_binary: Path) -> bytes:
    placeholder = b"__IHEAR_NODE_BINARY__"
    if template.count(placeholder) != 1 or not node_binary.is_absolute() or ".." in node_binary.parts:
        fail("web_service_template_invalid")
    return template.replace(placeholder, str(node_binary).encode("utf-8"))


def canonical_node_binary(source_root: Path) -> Path:
    operator = pwd.getpwnam("ondrej")
    module = load_module(
        source_root / "ops/linux/install.py", "ihear_domain_runtime_install", uid=operator.pw_uid
    )
    try:
        node = Path(module.canonical_node_binary())
    except Exception as error:
        raise InstallError("node_binary_invalid") from error
    if not node.is_absolute() or not node.is_file() or not os.access(node, os.X_OK):
        fail("node_binary_invalid")
    return node


def run_validation(*, nginx_created: bool, nginx_content: bytes) -> None:
    try:
        subprocess.run(
            ["systemd-analyze", "verify", "/etc/systemd/system/ihear-domain-web.service",
             "/etc/systemd/system/ihear-domain-tunnel.service"],
            check=True,
        )
    except subprocess.CalledProcessError as error:
        raise InstallError("configuration_validation_failed") from error
    try:
        subprocess.run(["nginx", "-t"], check=True)
    except subprocess.CalledProcessError as error:
        if nginx_created:
            path = Path("/etc/nginx/conf.d/ihear-domain.conf")
            try:
                metadata = path.lstat()
                if (
                    not stat.S_ISLNK(metadata.st_mode)
                    and stat.S_ISREG(metadata.st_mode)
                    and stat.S_IMODE(metadata.st_mode) == 0o600
                    and metadata.st_uid == 0
                    and metadata.st_gid == 0
                    and path.read_bytes() == nginx_content
                ):
                    path.unlink()
            except OSError:
                pass
        raise InstallError("configuration_validation_failed") from error


def ensure_access_log(path: Path, *, uid: int, gid: int) -> bool:
    """Create the log once; an existing valid log is append-only state, never content-compared."""
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return install_exact_bytes(path, b"", mode=0o640, uid=uid, gid=gid)
    except OSError as error:
        raise InstallError("target_file_unavailable") from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o640
        or metadata.st_uid != uid
        or metadata.st_gid != gid
    ):
        fail("target_file_conflict")
    return False


def install(args: argparse.Namespace) -> None:
    require_root()
    stage_root = verified_stage_root(args.stage_root)
    require_staged_directory(stage_root)
    source_root = args.source_root
    _, domain_access = validate_runtime(stage_root, source_root, EXPECTED_RUNTIME_HEAD)
    node_binary = canonical_node_binary(source_root)
    require_regular(Path("/opt/ihear/node"), mode=0o755, uid=0)
    token = validate_token(
        args.token_source,
        expected_account_id=args.expected_token_account_id,
        expected_tunnel_id=args.expected_token_tunnel_id,
        expected_sha256=args.expected_token_sha256,
    )
    if file_digest(args.cloudflared_source) != EXPECTED_CLOUDFLARED_SHA256:
        fail("cloudflared_digest_invalid")
    ensure_domain_account()
    www_data = pwd.getpwnam("www-data")

    require_directory(DOMAIN_ROOT, mode=0o755, uid=0, gid=0)
    require_directory(DOMAIN_ROOT / "scripts", mode=0o755, uid=0, gid=0)
    require_directory(DOMAIN_CONFIG, mode=0o700, uid=0, gid=0)
    require_directory(Path("/srv/ihear-domain"), mode=0o755, uid=0, gid=0)
    require_directory(DOMAIN_LOG, mode=0o750, uid=www_data.pw_uid, gid=0)

    access_document = domain_access.render_review_manifest(
        ACCESS_AUD,
        ACCESS_TEAM_DOMAIN,
        git_head=EXPECTED_RUNTIME_HEAD,
        next_build_id=EXPECTED_RUNTIME_BUILD_ID,
        tunnel_id=EXPECTED_TUNNEL_ID,
        token_sha256=args.expected_token_sha256,
    ).encode("utf-8") + b"\n"
    domain_sources = {
        "/etc/systemd/system/ihear-domain-web.service": render_web_service(
            read_stage_file(stage_root, "ops/domain/ihear-domain-web.service"), node_binary
        ),
        "/etc/systemd/system/ihear-domain-tunnel.service": read_stage_file(
            stage_root, "ops/domain/ihear-domain-tunnel.service"
        ),
        "/etc/nginx/conf.d/ihear-domain.conf": read_stage_file(stage_root, "ops/domain/nginx.conf.template"),
        "/etc/logrotate.d/ihear-domain": read_stage_file(stage_root, "ops/domain/logrotate-ihear-domain"),
        "/etc/systemd/journald@ihear-domain.conf.d/limits.conf": read_stage_file(
            stage_root, "ops/domain/journald-ihear-domain.conf"
        ),
        "/opt/ihear-domain/scripts/domain_access.py": read_stage_file(stage_root, "scripts/domain_access.py"),
        "/opt/ihear-domain/scripts/runtime_identity.py": read_stage_file(stage_root, "scripts/runtime_identity.py"),
        "/etc/ihear-domain/access.json": access_document,
        "/etc/ihear-domain/web.env": b"APP_PUBLIC_ORIGIN=https://ihear.ofops.co\n",
    }
    require_directory(Path("/etc/systemd/journald@ihear-domain.conf.d"), mode=0o755, uid=0, gid=0)
    nginx_created = False
    for raw_path, content in domain_sources.items():
        path = Path(raw_path)
        mode = 0o600 if path.parent == DOMAIN_CONFIG or path.suffix == ".conf" and "nginx" in str(path) else 0o644
        created = install_exact_bytes(path, content, mode=mode, uid=0, gid=0)
        nginx_created = nginx_created or (path == Path("/etc/nginx/conf.d/ihear-domain.conf") and created)

    install_exact_bytes(DOMAIN_CONFIG / "tunnel.token", token, mode=0o400, uid=0, gid=0)
    ensure_access_log(DOMAIN_LOG / "access.jsonl", uid=www_data.pw_uid, gid=0)
    install_cloudflared(args.cloudflared_source)
    run_validation(
        nginx_created=nginx_created,
        nginx_content=domain_sources["/etc/nginx/conf.d/ihear-domain.conf"],
    )
    sys.modules["runtime_identity"] = load_module(
        DOMAIN_ROOT / "scripts/runtime_identity.py", "ihear_domain_installed_runtime_identity", uid=0
    )
    installed_domain_access = load_module(
        DOMAIN_ROOT / "scripts/domain_access.py", "ihear_domain_installed_access", uid=0
    )
    try:
        installed_domain_access.preflight(source_root=source_root, config_root=DOMAIN_CONFIG)
    except Exception as error:
        raise InstallError("installed_preflight_failed") from error


def verified_stage_root(path: Path) -> Path:
    """Reject a symlink at any supplied stage-path component before canonicalizing it."""
    if not path.is_absolute():
        fail("stage_directory_invalid")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            metadata = current.lstat()
        except OSError as error:
            raise InstallError("stage_directory_missing") from error
        if stat.S_ISLNK(metadata.st_mode):
            fail("stage_directory_invalid")
        if not stat.S_ISDIR(metadata.st_mode):
            fail("stage_directory_invalid")
    return current


def main() -> int:
    parser = argparse.ArgumentParser(description="Install iHear domain artifacts without activation.")
    parser.add_argument("--stage-root", type=Path, default=DEFAULT_STAGE_ROOT)
    parser.add_argument("--source-root", type=Path, default=RUNTIME_ROOT)
    parser.add_argument("--cloudflared-source", type=Path, required=True)
    parser.add_argument("--token-source", type=Path, required=True)
    parser.add_argument("--expected-token-account-id", required=True)
    parser.add_argument("--expected-token-tunnel-id", required=True)
    parser.add_argument("--expected-token-sha256", required=True)
    args = parser.parse_args()
    try:
        install(args)
    except (InstallError, KeyError, OSError, subprocess.SubprocessError):
        print(json.dumps({"installed": False, "reason": "preflight_or_install_failed"}, sort_keys=True))
        return 1
    print(json.dumps({"installed": True, "activated": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
