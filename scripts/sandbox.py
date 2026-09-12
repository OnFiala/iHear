#!/usr/bin/env python3
"""Read-only identity-bound inspection of the configured iHear Linux sandbox."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BINDING = ROOT / ".local/sandbox/host.json"


def command(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=True, text=True, capture_output=True, timeout=30, **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "binding"], default="status", nargs="?")
    args = parser.parse_args()
    if not BINDING.is_file():
        raise RuntimeError(f"Missing private host binding: {BINDING}")
    target = json.loads(BINDING.read_text())
    if args.action == "binding":
        print(json.dumps({"configured": True, "schemaVersion": target.get("schema_version")}))
        return
    alias = target["ssh_alias"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", alias):
        raise RuntimeError("Invalid SSH alias in host binding")
    effective = command(["ssh", "-G", alias]).stdout
    config = {}
    for line in effective.splitlines():
        key, _, value = line.partition(" ")
        config.setdefault(key, []).append(value)
    expected = {
        "user": target["user"], "hostname": target["ssh_hostname"],
        "hostkeyalias": target["host_key_alias"], "identityfile": target["identity_file"],
    }
    for key, value in expected.items():
        if config.get(key) != [value]:
            raise RuntimeError(f"SSH configuration mismatch for {key}; inspect the canonical alias")
    if config.get("stricthostkeychecking") not in (["true"], ["yes"]):
        raise RuntimeError("Strict host key checking must be enabled")
    if config.get("identitiesonly") != ["yes"]:
        raise RuntimeError("SSH must use only the configured identity")
    if config.get("proxycommand", ["none"]) != ["none"] or config.get("proxyjump", ["none"]) != ["none"]:
        raise RuntimeError("Unexpected SSH proxy; revalidate the host binding")
    remote_root = target["runtime_root"]
    if not remote_root.startswith("/") or "\n" in remote_root:
        raise RuntimeError("Runtime root must be an absolute path")
    guard = "\n".join([
        "set -eu",
        f"test \"$(hostname)\" = {shlex.quote(target['hostname'])}",
        f"test \"$(id -un)\" = {shlex.quote(target['user'])}",
        f"test \"$(getent passwd \"$(id -un)\" | cut -d: -f6)\" = {shlex.quote(target['home'])}",
        f"test \"$(ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub | awk '{{print $2}}')\" = {shlex.quote(target['host_key_fingerprint'])}",
        "printf 'Identity verified\\n'", "uptime", "free -h", "df -h /",
        f"cd {shlex.quote(remote_root)}", "git status --short --branch", "git rev-parse HEAD",
        "python3 scripts/linux.py status",
        "systemctl is-active ihear-stack.service ihear-web.service ihear-monitor-dashboard.service ihear-monitor-collector.timer || true",
        "systemctl --user is-active openclaw-gateway.service || true",
    ])
    result = command(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "ConnectionAttempts=1", alias, "bash -s"], input=guard)
    print(result.stdout, end="")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, KeyError, ValueError, subprocess.SubprocessError) as exc:
        # Do not print command payloads or runtime environment contents.
        print("Sandbox inspection failed. Check the private binding, strict SSH identity and host availability locally.", file=sys.stderr)
        sys.exit(1)
