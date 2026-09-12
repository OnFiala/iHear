#!/usr/bin/env python3
"""Read-only checks for the isolated iHear owner-only domain route.

This helper never creates cloud resources, installs units, writes configuration,
or prints credentials. It hashes the protected token to reject a wrong connector.
Cloudflare Access is enforced by the dedicated Tunnel
setting; this code only makes its exact non-secret binding reviewable before an
owner activates the route.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import pwd
import re
import stat
import subprocess
from urllib.parse import urlsplit

from runtime_identity import validate_runtime_identity


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_HOST = "ihear.ofops.co"
DOMAIN_ORIGIN = f"https://{DOMAIN_HOST}"
DOMAIN_WEB_PORT = 3001
DOMAIN_NGINX_PORT = 8081
EXPECTED_SOURCE_ROOT = Path("/home/ondrej/iHear")
EXPECTED_CONFIG_ROOT = Path("/etc/ihear-domain")
ACCESS_BINDING_NAME = "access.json"
WEB_ENV_NAME = "web.env"
TUNNEL_TOKEN_NAME = "tunnel.token"
TUNNEL_BINARY = Path("/opt/ihear-domain/cloudflared")
PRIVATE_NGINX_TEMPLATE = Path("ops/monitor/nginx/ihear.conf.template")
PRIVATE_NGINX_CONFIG = Path("/etc/nginx/conf.d/ihear.conf")
PRIVATE_LOGIN_PLACEHOLDER = "__IHEAR_PRIVATE_LOGIN__"
ACCESS_AUD_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,256}$")


class DomainAccessError(RuntimeError):
    """A deliberately non-sensitive reason why activation is unsafe."""


@dataclass(frozen=True)
class AccessBinding:
    access_aud: str
    access_team_domain: str


@dataclass(frozen=True)
class RuntimeBinding(AccessBinding):
    git_head: str
    next_build_id: str
    tunnel_id: str
    token_sha256: str


def validate_access_binding(access_aud: object, access_team_domain: object) -> AccessBinding:
    """Validate the non-secret Access application binding exactly enough to pin it."""
    if not isinstance(access_aud, str) or not ACCESS_AUD_PATTERN.fullmatch(access_aud):
        raise DomainAccessError("access_binding_invalid")
    if not isinstance(access_team_domain, str):
        raise DomainAccessError("access_binding_invalid")
    parsed = urlsplit(access_team_domain)
    hostname = parsed.hostname
    try:
        port = parsed.port
    except ValueError as error:
        raise DomainAccessError("access_binding_invalid") from error
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or hostname.lower() != hostname
        or not hostname.isascii()
        or not hostname.endswith(".cloudflareaccess.com")
        or hostname == "cloudflareaccess.com"
        or any(part == "" for part in hostname.split("."))
        or access_team_domain != f"https://{hostname}"
    ):
        raise DomainAccessError("access_binding_invalid")
    return AccessBinding(access_aud=access_aud, access_team_domain=f"https://{hostname}")


def validate_binding_document(document: object) -> RuntimeBinding:
    if not isinstance(document, dict) or set(document) != {
        "schemaVersion", "hostname", "appOrigin", "webPort", "nginxPort", "accessAud",
        "accessTeamDomain", "expectedGitHead", "expectedNextBuildId",
        "expectedTunnelId", "tokenSha256",
    }:
        raise DomainAccessError("access_binding_invalid")
    if document["schemaVersion"] != 1:
        raise DomainAccessError("access_binding_invalid")
    if (
        document["hostname"] != DOMAIN_HOST
        or document["appOrigin"] != DOMAIN_ORIGIN
        or document["webPort"] != DOMAIN_WEB_PORT
        or document["nginxPort"] != DOMAIN_NGINX_PORT
    ):
        raise DomainAccessError("access_binding_invalid")
    for key, pattern in (
        ("expectedGitHead", r"[0-9a-f]{40}"),
        ("expectedNextBuildId", r"[A-Za-z0-9_-]{1,100}"),
        ("expectedTunnelId", r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"),
        ("tokenSha256", r"[0-9a-f]{64}"),
    ):
        if not isinstance(document[key], str) or not re.fullmatch(pattern, document[key]):
            raise DomainAccessError("access_binding_invalid")
    access = validate_access_binding(document["accessAud"], document["accessTeamDomain"])
    return RuntimeBinding(access.access_aud, access.access_team_domain,
                          document["expectedGitHead"], document["expectedNextBuildId"],
                          document["expectedTunnelId"], document["tokenSha256"])


def validate_web_override(text: str) -> None:
    """Permit only the one domain-specific application override."""
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            raise DomainAccessError("web_override_invalid")
        key, value = line.split("=", 1)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or key in values:
            raise DomainAccessError("web_override_invalid")
        values[key] = value
    if values != {"APP_PUBLIC_ORIGIN": DOMAIN_ORIGIN}:
        raise DomainAccessError("web_override_invalid")


def require_regular_file(path: Path, *, mode: int, uid: int) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise DomainAccessError("protected_file_missing") from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != mode
        or metadata.st_uid != uid
    ):
        raise DomainAccessError("protected_file_invalid")


def require_private_directory(path: Path, *, mode: int, uid: int) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise DomainAccessError("protected_file_missing") from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != mode
        or metadata.st_uid != uid
    ):
        raise DomainAccessError("protected_file_invalid")


def read_protected_text(path: Path, *, mode: int, uid: int) -> str:
    require_regular_file(path, mode=mode, uid=uid)
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise DomainAccessError("protected_file_unreadable") from error


def read_access_binding(config_root: Path) -> RuntimeBinding:
    text = read_protected_text(config_root / ACCESS_BINDING_NAME, mode=0o600, uid=0)
    try:
        document = json.loads(text)
    except json.JSONDecodeError as error:
        raise DomainAccessError("access_binding_invalid") from error
    return validate_binding_document(document)


def validate_root_runtime_identity(source_root: Path) -> None:
    if platform.system() != "Linux" or os.geteuid() != 0:
        raise DomainAccessError("root_runtime_required")
    if source_root.resolve() != EXPECTED_SOURCE_ROOT.resolve():
        raise DomainAccessError("source_root_invalid")
    try:
        operator = pwd.getpwnam("ondrej")
        validate_runtime_identity(
            source_root / ".local/sandbox/runtime.json", expected_uid=operator.pw_uid
        )
    except (KeyError, OSError, RuntimeError) as error:
        raise DomainAccessError("runtime_identity_invalid") from error


def frozen_source_evidence(source_root: Path, binding: RuntimeBinding | None = None) -> None:
    """Require a clean committed checkout and a matching prepared web artifact."""
    try:
        operator = pwd.getpwnam("ondrej")
    except KeyError as error:
        raise DomainAccessError("source_identity_unavailable") from error

    def git(*arguments: str) -> str:
        result = subprocess.run(
            ["runuser", "--user", operator.pw_name, "--", "git", "-C", str(source_root), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise DomainAccessError("source_identity_unavailable")
        return result.stdout.strip()

    if git("status", "--porcelain", "--untracked-files=all"):
        raise DomainAccessError("source_not_frozen")
    head = git("rev-parse", "--verify", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise DomainAccessError("source_identity_unavailable")
    manifest_path = source_root / ".local/linux-artifacts.json"
    manifest_text = read_protected_text(manifest_path, mode=0o600, uid=operator.pw_uid)
    build_path = source_root / ".next/BUILD_ID"
    build_id = read_protected_text(build_path, mode=0o644, uid=operator.pw_uid).strip()
    try:
        manifest = json.loads(manifest_text)
    except json.JSONDecodeError as error:
        raise DomainAccessError("artifact_manifest_invalid") from error
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {"schemaVersion", "gitHead", "workerImageId", "nextBuildId"}
        or manifest.get("schemaVersion") != 1
        or manifest.get("gitHead") != head
        or manifest.get("nextBuildId") != build_id
        or not isinstance(manifest.get("workerImageId"), str)
        or not manifest["workerImageId"]
        or not build_id
    ):
        raise DomainAccessError("artifact_identity_mismatch")
    if binding is not None and (head != binding.git_head or build_id != binding.next_build_id):
        raise DomainAccessError("reviewed_artifact_mismatch")


def validate_tunnel_token(path: Path, binding: RuntimeBinding) -> None:
    """Read only the scoped credential; never include its value in errors."""
    require_regular_file(path, mode=0o400, uid=0)
    try:
        token = path.read_bytes()
        if hashlib.sha256(token).hexdigest() != binding.token_sha256:
            raise ValueError
        document = json.loads(base64.b64decode(token, validate=True))
        if document.get("t") != binding.tunnel_id or not isinstance(document.get("s"), str):
            raise ValueError
    except (OSError, ValueError, TypeError, AttributeError):
        raise DomainAccessError("tunnel_token_mismatch") from None


def validate_private_login(login: object) -> str:
    if not isinstance(login, str) or not re.fullmatch(r"[A-Za-z0-9_.+@-]+", login):
        raise DomainAccessError("private_validator_invalid")
    return login


def render_private_nginx(template: str, login: object) -> str:
    """Mirror the private installer render without exposing its owner identity."""
    login = validate_private_login(login)
    quoted_placeholder = f'"{PRIVATE_LOGIN_PLACEHOLDER}"'
    if template.count(PRIVATE_LOGIN_PLACEHOLDER) != 1 or template.count(quoted_placeholder) != 1:
        raise DomainAccessError("private_validator_invalid")
    return template.replace(quoted_placeholder, f'"{login}"')


def observed_private_login() -> str:
    """Read the current tailnet owner login only for the remote validator binding."""
    result = subprocess.run(
        ["tailscale", "status", "--json"], text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise DomainAccessError("private_validator_unavailable")
    try:
        state = json.loads(result.stdout)
        return validate_private_login(state["User"][str(state["Self"]["UserID"])]["LoginName"])
    except (KeyError, TypeError, json.JSONDecodeError, DomainAccessError) as error:
        raise DomainAccessError("private_validator_unavailable") from error


def private_config_matches(template: str, installed: bytes, login: object) -> bool:
    return installed == render_private_nginx(template, login).encode("utf-8")


def validate_private_validator(source_root: Path) -> None:
    """Bind the rendered private proxy byte-for-byte to its observed owner identity."""
    try:
        template = (source_root / PRIVATE_NGINX_TEMPLATE).read_text(encoding="utf-8")
        require_regular_file(PRIVATE_NGINX_CONFIG, mode=0o600, uid=0)
        installed = PRIVATE_NGINX_CONFIG.read_bytes()
        matches = private_config_matches(template, installed, observed_private_login())
    except (OSError, DomainAccessError) as error:
        raise DomainAccessError("private_validator_unavailable") from error
    if not matches:
        raise DomainAccessError("private_validator_invalid")


def validate_tunnel_binary(path: Path = TUNNEL_BINARY) -> None:
    """Require a root-pinned cloudflared with token-file support before activation."""
    require_regular_file(path, mode=0o755, uid=0)
    result = subprocess.run([str(path), "--version"], text=True, capture_output=True, check=False)
    match = re.search(r"\b(20\d{2})\.(\d+)\.(\d+)\b", result.stdout)
    if result.returncode != 0 or match is None:
        raise DomainAccessError("tunnel_binary_invalid")
    version = tuple(int(part) for part in match.groups())
    if version < (2025, 4, 0):
        raise DomainAccessError("tunnel_binary_unsupported")


def preflight(
    *, source_root: Path = EXPECTED_SOURCE_ROOT,
    config_root: Path = EXPECTED_CONFIG_ROOT,
) -> RuntimeBinding:
    """Read-only activation gate; no system or Cloudflare state is changed."""
    validate_root_runtime_identity(source_root)
    require_private_directory(config_root, mode=0o700, uid=0)
    binding = read_access_binding(config_root)
    validate_web_override(read_protected_text(config_root / WEB_ENV_NAME, mode=0o600, uid=0))
    validate_tunnel_token(config_root / TUNNEL_TOKEN_NAME, binding)
    try:
        operator_uid = pwd.getpwnam("ondrej").pw_uid
    except KeyError as error:
        raise DomainAccessError("source_identity_unavailable") from error
    require_regular_file(source_root / ".env.local", mode=0o600, uid=operator_uid)
    frozen_source_evidence(source_root, binding)
    validate_private_validator(source_root)
    validate_tunnel_binary()
    return binding


def safe_status(*, source_root: Path, config_root: Path) -> dict[str, bool | str]:
    try:
        preflight(
            source_root=source_root,
            config_root=config_root,
        )
    except DomainAccessError as error:
        return {"localPreflightReady": False, "reason": str(error)}
    return {"localPreflightReady": True, "reason": "local_checks_only", "liveAccessVerified": False}


def render_review_manifest(access_aud: str, access_team_domain: str, *, git_head: str,
                           next_build_id: str, tunnel_id: str, token_sha256: str) -> str:
    """Render a non-secret review record; it is never written by this helper."""
    binding = validate_access_binding(access_aud, access_team_domain)
    document = {
            "schemaVersion": 1,
            "hostname": DOMAIN_HOST,
            "appOrigin": DOMAIN_ORIGIN,
            "webPort": DOMAIN_WEB_PORT,
            "nginxPort": DOMAIN_NGINX_PORT,
            "accessAud": binding.access_aud,
            "accessTeamDomain": binding.access_team_domain,
            "expectedGitHead": git_head,
            "expectedNextBuildId": next_build_id,
            "expectedTunnelId": tunnel_id,
            "tokenSha256": token_sha256,
        }
    validate_binding_document(document)
    return json.dumps(document, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only iHear domain-route validation.")
    commands = parser.add_subparsers(dest="command", required=True)
    render = commands.add_parser("render-review-manifest")
    render.add_argument("--access-aud", required=True)
    render.add_argument("--access-team-domain", required=True)
    render.add_argument("--git-head", required=True)
    render.add_argument("--next-build-id", required=True)
    render.add_argument("--tunnel-id", required=True)
    render.add_argument("--token-sha256", required=True)
    for name in ("status", "preflight"):
        command = commands.add_parser(name)
        command.add_argument("--source-root", type=Path, default=EXPECTED_SOURCE_ROOT)
        command.add_argument("--config-root", type=Path, default=EXPECTED_CONFIG_ROOT)
    args = parser.parse_args()
    try:
        if args.command == "render-review-manifest":
            print(render_review_manifest(args.access_aud, args.access_team_domain,
                  git_head=args.git_head, next_build_id=args.next_build_id,
                  tunnel_id=args.tunnel_id, token_sha256=args.token_sha256))
            return 0
        result = safe_status(
            source_root=args.source_root,
            config_root=args.config_root,
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["localPreflightReady"] else 1
    except DomainAccessError as error:
        print(json.dumps({"localPreflightReady": False, "reason": str(error)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
