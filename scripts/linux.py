#!/usr/bin/env python3
"""Prepare and operate the dedicated iHear Ubuntu runtime.

The web process is intentionally excluded: systemd owns it on Linux. This script
only manages the local Supabase stack and the iHear worker container.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import platform
import pwd
import socket
import subprocess
from typing import Any
from urllib.parse import urlsplit

import local as local_runtime


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
EXPECTED_ROOT = Path("/home/ondrej/iHear")
EXPECTED_HOME = Path("/home/ondrej")
EXPECTED_HOSTNAME = "openclaw-appliance"
LOCAL_BIN = EXPECTED_HOME / ".local/bin"
NODE_BIN = LOCAL_BIN / "node"
PNPM_BIN = LOCAL_BIN / "pnpm"
SUPABASE_NETWORK = "supabase_network_iHear"
SUPABASE_DB = "supabase_db_iHear"
SUPABASE_KONG = "supabase_kong_iHear"
WORKER_IMAGE = "ihear-worker:local"
ARTIFACT_MANIFEST = LOCAL / "linux-artifacts.json"
COMPOSE = [
    "docker",
    "compose",
    "-p",
    "ihear",
    "-f",
    "docker-compose.yml",
    "-f",
    "docker-compose.linux.yml",
]


def run(
    command: list[str],
    *,
    env: dict[str, str],
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a project command without including captured output in failures."""
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        check=False,
        text=True,
        capture_output=capture,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"{command[0]} command failed with exit code {result.returncode}.")
    return result


def runtime_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = f"{LOCAL_BIN}:{env.get('PATH', '')}"
    env["OPENAI_API_KEY"] = ""
    return env


def parse_os_release(path: Path = Path("/etc/os-release")) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"')
    return values


def validate_host() -> None:
    if platform.system() != "Linux":
        raise RuntimeError("This command is restricted to the dedicated Linux runtime.")
    if platform.machine().lower() not in {"x86_64", "amd64"}:
        raise RuntimeError("The dedicated runtime must be x86_64.")
    release = parse_os_release()
    if release.get("ID") != "ubuntu" or release.get("VERSION_ID") != "24.04":
        raise RuntimeError("The dedicated runtime must run Ubuntu 24.04.")
    if ROOT.resolve() != EXPECTED_ROOT:
        raise RuntimeError(f"Run the canonical checkout at {EXPECTED_ROOT}.")
    if socket.gethostname() != EXPECTED_HOSTNAME:
        raise RuntimeError(f"The dedicated runtime hostname must be {EXPECTED_HOSTNAME}.")
    operator = pwd.getpwuid(os.geteuid())
    if Path(operator.pw_dir).resolve() != EXPECTED_HOME or operator.pw_name != "ondrej":
        raise RuntimeError("Run this command as operator ondrej with home /home/ondrej.")


def validate_tools(env: dict[str, str], *, require_daemon: bool = True) -> None:
    for executable, label in ((NODE_BIN, "Node.js"), (PNPM_BIN, "pnpm")):
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise RuntimeError(f"{label} must be installed at {executable}.")
    run([str(NODE_BIN), "--version"], env=env, capture=True)
    run([str(PNPM_BIN), "--version"], env=env, capture=True)
    node = run(
        [str(PNPM_BIN), "exec", "node", "-p", "process.execPath"],
        env=env,
        capture=True,
    )
    if Path(node.stdout.strip()).resolve() != NODE_BIN.resolve():
        raise RuntimeError(f"pnpm must use the dedicated Node.js binary at {NODE_BIN}.")
    run([str(PNPM_BIN), "exec", "supabase", "--version"], env=env, capture=True)
    run(["docker", "compose", "version"], env=env, capture=True)
    context = run(
        ["docker", "context", "inspect", "--format", "{{json .Endpoints.docker.Host}}"],
        env=env,
        capture=True,
    )
    docker_host = json.loads(context.stdout)
    if docker_host != "unix:///var/run/docker.sock":
        raise RuntimeError("Docker Engine must use the local /var/run/docker.sock daemon.")
    configured_host = env.get("DOCKER_HOST")
    if configured_host and configured_host != docker_host:
        raise RuntimeError("DOCKER_HOST must not redirect the dedicated runtime to another daemon.")
    if not require_daemon:
        return
    result = run(
        ["docker", "info", "--format", "{{json .}}"],
        env=env,
        capture=True,
    )
    info = json.loads(result.stdout)
    if info.get("OSType") != "linux" or info.get("Architecture") not in {"x86_64", "amd64"}:
        raise RuntimeError("Docker Engine must use the native Linux x86_64 daemon.")
    if "desktop" in str(info.get("OperatingSystem", "")).lower():
        raise RuntimeError("Docker Desktop is not accepted for the dedicated Linux runtime.")


def ensure_docker_loopback_default(path: Path = Path("/etc/docker/daemon.json")) -> None:
    try:
        settings = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("A readable valid /etc/docker/daemon.json is required.") from error
    if settings.get("ip") != "127.0.0.1":
        raise RuntimeError('Docker must set "ip": "127.0.0.1" before Supabase starts.')


def clean_git_head(env: dict[str, str]) -> str:
    result = run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        env=env,
        capture=True,
    )
    if result.stdout.strip():
        raise RuntimeError("The iHear checkout must be clean and committed before prepare or start.")
    head = run(["git", "rev-parse", "--verify", "HEAD"], env=env, capture=True).stdout.strip()
    if not head:
        raise RuntimeError("The iHear checkout has no committed HEAD.")
    return head


def validate_private_origin(origin: str | None) -> str:
    if not origin:
        raise RuntimeError("A private HTTPS APP_PUBLIC_ORIGIN is required; run prepare --origin first.")
    parsed = urlsplit(origin)
    hostname = parsed.hostname
    try:
        parsed.port
    except ValueError as error:
        raise RuntimeError("APP_PUBLIC_ORIGIN contains an invalid port.") from error
    if (
        parsed.scheme != "https"
        or not hostname
        or any(character.isspace() for character in origin)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError("APP_PUBLIC_ORIGIN must be a private HTTPS origin without credentials or a path.")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise RuntimeError("APP_PUBLIC_ORIGIN must not use localhost.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if address.is_loopback or address.is_unspecified:
            raise RuntimeError("APP_PUBLIC_ORIGIN must not use a loopback or unspecified address.")
    return origin.rstrip("/")


def ensure_expected_origin(env: dict[str, str], origin: str | None) -> str:
    origin = validate_private_origin(origin)
    result = run(["tailscale", "status", "--json"], env=env, capture=True)
    try:
        status = json.loads(result.stdout)
        dns_name = str(status["Self"]["DNSName"]).rstrip(".").lower()
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise RuntimeError("Tailscale did not report this node's DNS name.") from error
    if not dns_name:
        raise RuntimeError("Tailscale did not report this node's DNS name.")
    parsed = urlsplit(origin)
    if parsed.hostname.lower() != dns_name or parsed.port != 8446:
        raise RuntimeError("APP_PUBLIC_ORIGIN must match this Tailscale node DNS name on HTTPS port 8446.")
    return f"https://{dns_name}:8446"


def existing_start_origin() -> str:
    path = ROOT / ".env.local"
    if not path.exists():
        raise RuntimeError(".env.local is missing; run prepare --origin before start.")
    if path.stat().st_mode & 0o777 != 0o600:
        raise RuntimeError(".env.local must have mode 0600.")
    return validate_private_origin(local_runtime.read_env().get("APP_PUBLIC_ORIGIN"))


def current_worker_image_id(env: dict[str, str]) -> str:
    result = run(
        ["docker", "image", "inspect", WORKER_IMAGE, "--format", "{{.Id}}"],
        env=env,
        capture=True,
    )
    image_id = result.stdout.strip()
    if not image_id:
        raise RuntimeError("The prepared iHear worker image is missing.")
    return image_id


def current_next_build_id() -> str:
    path = ROOT / ".next/BUILD_ID"
    try:
        build_id = path.read_text().strip()
    except OSError as error:
        raise RuntimeError("The prepared Next.js BUILD_ID is missing.") from error
    if not build_id:
        raise RuntimeError("The prepared Next.js BUILD_ID is empty.")
    return build_id


def write_artifact_manifest(env: dict[str, str], git_head: str) -> None:
    manifest = {
        "schemaVersion": 1,
        "gitHead": git_head,
        "workerImageId": current_worker_image_id(env),
        "nextBuildId": current_next_build_id(),
    }
    LOCAL.mkdir(mode=0o700, exist_ok=True)
    LOCAL.chmod(0o700)
    temporary = LOCAL / "linux-artifacts.json.tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as file:
        json.dump(manifest, file, sort_keys=True)
        file.write("\n")
    temporary.chmod(0o600)
    os.replace(temporary, ARTIFACT_MANIFEST)
    ARTIFACT_MANIFEST.chmod(0o600)


def verify_artifact_manifest(env: dict[str, str], git_head: str) -> None:
    try:
        if ARTIFACT_MANIFEST.stat().st_mode & 0o777 != 0o600:
            raise RuntimeError("The Linux artifact manifest must have mode 0600.")
        manifest = json.loads(ARTIFACT_MANIFEST.read_text())
    except FileNotFoundError as error:
        raise RuntimeError("Linux artifacts are not prepared; run prepare --origin first.") from error
    except json.JSONDecodeError as error:
        raise RuntimeError("The Linux artifact manifest is invalid; run prepare --origin again.") from error
    expected = {
        "schemaVersion": 1,
        "gitHead": git_head,
        "workerImageId": current_worker_image_id(env),
        "nextBuildId": current_next_build_id(),
    }
    if manifest != expected:
        raise RuntimeError("Linux source or artifacts drifted; run prepare --origin again.")


def protected_log(name: str, command: list[str], env: dict[str, str]) -> None:
    LOCAL.mkdir(exist_ok=True)
    path = LOCAL / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as file:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            stdout=file,
            stderr=subprocess.STDOUT,
            check=False,
            text=True,
        )
    path.chmod(0o600)
    if result.returncode != 0:
        raise RuntimeError(f"{command[0]} command failed; inspect {path} as operator ondrej.")


def supabase_containers(env: dict[str, str]) -> list[tuple[str, str]]:
    result = run(
        ["docker", "ps", "-a", "--format", "{{.ID}}\t{{.Names}}"],
        env=env,
        capture=True,
    )
    containers: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        container_id, separator, name = line.partition("\t")
        if separator and name.endswith("_iHear") and name.startswith("supabase_"):
            containers.append((container_id, name))
    return containers


def ensure_loopback_bindings(env: dict[str, str], *, require_containers: bool = True) -> None:
    containers = supabase_containers(env)
    if not containers and require_containers:
        raise RuntimeError("No iHear Supabase containers were found after startup.")
    for container_id, name in containers:
        result = run(
            ["docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", container_id],
            env=env,
            capture=True,
        )
        ports = json.loads(result.stdout) or {}
        for bindings in ports.values():
            for binding in bindings or []:
                host_ip = binding.get("HostIp", "")
                try:
                    is_loopback = ipaddress.ip_address(host_ip).is_loopback
                except ValueError:
                    is_loopback = False
                if not is_loopback:
                    raise RuntimeError(
                        f"Container {name} publishes a port outside loopback; refusing to continue."
                    )


def network_container_names(env: dict[str, str]) -> set[str]:
    result = run(
        ["docker", "network", "inspect", SUPABASE_NETWORK, "--format", "{{json .Containers}}"],
        env=env,
        capture=True,
    )
    containers: dict[str, dict[str, Any]] = json.loads(result.stdout) or {}
    return {str(container.get("Name")) for container in containers.values()}


def ensure_supabase_network(env: dict[str, str]) -> None:
    names = network_container_names(env)
    missing = {SUPABASE_DB, SUPABASE_KONG} - names
    if missing:
        raise RuntimeError(
            "The iHear Supabase DB and API gateway are not attached to the expected external network."
        )


def ensure_worker_network(env: dict[str, str]) -> None:
    result = run(COMPOSE + ["ps", "-q", "worker"], env=env, capture=True)
    container_id = result.stdout.strip()
    if not container_id:
        raise RuntimeError("The iHear worker container is not running.")
    result = run(
        ["docker", "inspect", "--format", "{{json .NetworkSettings.Networks}}", container_id],
        env=env,
        capture=True,
    )
    networks = json.loads(result.stdout) or {}
    if SUPABASE_NETWORK not in networks:
        raise RuntimeError("The iHear worker did not join the Supabase external network.")


def ensure_offline_env(*, allow_missing: bool = False) -> None:
    values = local_runtime.read_env()
    if not values and allow_missing:
        return
    if values.get("OPENAI_API_KEY", ""):
        raise RuntimeError("OPENAI_API_KEY must remain empty on the dedicated offline runtime.")
    mode = (ROOT / ".env.local").stat().st_mode & 0o777
    if mode != 0o600:
        raise RuntimeError(".env.local must have mode 0600.")


def ensure_runtime_foundation(env: dict[str, str], origin: str | None) -> dict[str, str]:
    origin = validate_private_origin(origin)
    ensure_docker_loopback_default()
    ensure_loopback_bindings(env, require_containers=False)
    existing = local_runtime.read_env()
    # This laptop is explicitly authorized as an offline, no-provider runtime.
    # Announce removal of a pre-existing key without ever printing its value.
    if existing.get("OPENAI_API_KEY", ""):
        print("Clearing the existing OPENAI_API_KEY under the authorized offline-runtime policy.")
    protected_log(
        "supabase-start.linux.log",
        [str(PNPM_BIN), "exec", "supabase", "start"],
        env,
    )
    values = local_runtime.make_env(env, origin, force_offline=True)
    ensure_offline_env()
    ensure_supabase_network(env)
    ensure_loopback_bindings(env)
    run([str(PNPM_BIN), "exec", "supabase", "migration", "up", "--local"], env=env)
    return values


def prepare(env: dict[str, str], origin: str | None) -> None:
    origin = ensure_expected_origin(env, origin)
    git_head = clean_git_head(env)
    ensure_runtime_foundation(env, origin)
    run(COMPOSE + ["build", "--pull=false", "worker"], env=env)
    run([str(PNPM_BIN), "build"], env=env)
    if clean_git_head(env) != git_head:
        raise RuntimeError("The committed source changed during prepare; refusing to record artifacts.")
    write_artifact_manifest(env, git_head)
    print("iHear local foundation, Linux worker image and Next.js application are prepared.")


def start(env: dict[str, str]) -> None:
    origin = existing_start_origin()
    origin = ensure_expected_origin(env, origin)
    git_head = clean_git_head(env)
    verify_artifact_manifest(env, git_head)
    if clean_git_head(env) != git_head:
        raise RuntimeError("The committed source changed during start preflight.")
    values = ensure_runtime_foundation(env, origin)
    run(COMPOSE + ["up", "-d", "--no-build", "--pull", "never", "worker"], env=env)
    ensure_worker_network(env)
    print(
        "iHear Supabase and worker are running.\n"
        f"Web origin for the systemd service: {values['APP_PUBLIC_ORIGIN']}\n"
        "Supabase API: http://127.0.0.1:54321\n"
        "Studio: http://127.0.0.1:54323"
    )


def stop(env: dict[str, str]) -> None:
    run(COMPOSE + ["down"], env=env)
    protected_log(
        "supabase-stop.linux.log",
        [str(PNPM_BIN), "exec", "supabase", "stop"],
        env,
    )
    print("iHear worker and Supabase are stopped; local data and model volumes are preserved.")


def status(env: dict[str, str]) -> None:
    daemon = run(
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        env=env,
        capture=True,
        check=False,
    )
    if daemon.returncode != 0:
        print(json.dumps({"dockerRunning": False, "supabaseRunning": False, "workerRunning": False}, indent=2))
        return
    supabase = run(
        [str(PNPM_BIN), "exec", "supabase", "status", "-o", "json"],
        env=env,
        capture=True,
        check=False,
    )
    worker = run(COMPOSE + ["ps", "-q", "worker"], env=env, capture=True, check=False)
    payload = {
        "dockerRunning": True,
        "supabaseRunning": supabase.returncode == 0,
        "workerRunning": worker.returncode == 0 and bool(worker.stdout.strip()),
        "webManagedBy": "systemd",
        "pairingOrigin": local_runtime.read_env().get("APP_PUBLIC_ORIGIN"),
    }
    print(json.dumps(payload, indent=2))
    if supabase.returncode == 0:
        ensure_loopback_bindings(env)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "start", "stop", "status"])
    parser.add_argument(
        "--origin",
        help="Reachable private HTTPS origin for pairing; localhost is desktop-only.",
    )
    args = parser.parse_args()
    if args.action == "prepare" and not args.origin:
        parser.error("prepare requires --origin with the private HTTPS application origin.")
    if args.action != "prepare" and args.origin:
        parser.error("--origin is accepted only by prepare; start uses the prepared .env.local.")
    validate_host()
    env = runtime_env()
    validate_tools(env, require_daemon=args.action != "status")
    if args.action == "prepare":
        prepare(env, args.origin)
    elif args.action == "start":
        start(env)
    elif args.action == "stop":
        stop(env)
    else:
        status(env)


if __name__ == "__main__":
    main()
