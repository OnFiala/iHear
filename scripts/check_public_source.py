#!/usr/bin/env python3
"""Reject private sandbox identities and sensitive artifacts before publication.

Output names the file and rule, never the matched value. This is a focused
publication check, not a general secret scanner or an image/OCR audit.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_BINDING = ROOT / ".local/sandbox/host.json"
PRIVATE_FIELDS = (
    "hostname", "ssh_hostname", "ssh_alias", "lan_ssh_alias", "host_key_alias",
    "host_key_fingerprint", "identity_file", "origin", "dashboard_origin",
)
CONTENT_RULES = {
    "tailnet-address": re.compile(rb"(?:[a-z0-9-]+\.)+tail[0-9a-f]{4,}\.ts\.net", re.I),
    "private-key": re.compile(rb"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"),
    "provider-secret": re.compile(rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}"),
}
FORBIDDEN_PARTS = {
    ".local", "artifacts", "test-results", "playwright-report", "node_modules",
    ".next", ".venv", "__pycache__",
}
FORBIDDEN_SUFFIXES = {".wav", ".pcm", ".sqlite", ".sqlite3", ".db", ".pem", ".key"}


def private_values(binding: Path, required: bool = False) -> list[bytes]:
    if not binding.is_file():
        if required:
            raise ValueError("The ignored private sandbox binding is required for this check.")
        return []
    document = json.loads(binding.read_text())
    if not isinstance(document, dict):
        raise ValueError("The private sandbox binding must be an object.")
    values = []
    for field in PRIVATE_FIELDS:
        value = document.get(field)
        if isinstance(value, str) and len(value) >= 6:
            values.append(value.lower().encode())
        elif required:
            raise ValueError("The private sandbox identity binding is incomplete.")
    addresses = document.get("ip_addresses", [])
    if not isinstance(addresses, list) or (required and not addresses):
        raise ValueError("The private sandbox address binding is incomplete.")
    for address in addresses:
        if not isinstance(address, str):
            raise ValueError("The private sandbox address binding is invalid.")
        parsed = ipaddress.ip_address(address)
        # Include canonical and expanded IPv6 spellings without printing either.
        values.extend(value.lower().encode() for value in (address, str(parsed), parsed.exploded))
    return values


def inspect(path: str, data: bytes, private: list[bytes]) -> list[str]:
    name = Path(path)
    rules = []
    if FORBIDDEN_PARTS.intersection(name.parts) or name.suffix.lower() in FORBIDDEN_SUFFIXES:
        rules.append("private-artifact-path")
    if name.name.startswith(".env") and name.name != ".env.example":
        rules.append("environment-file")
    for label, pattern in CONTENT_RULES.items():
        if pattern.search(data):
            rules.append(label)
    lowered = data.lower()
    if any(value in lowered for value in private):
        rules.append("private-host-binding")
    return rules


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-binding", action="store_true")
    parser.add_argument("--ref", help="Inspect the exact committed tree instead of working files.")
    args = parser.parse_args()
    private = private_values(PRIVATE_BINDING, args.require_binding)
    paths = (git("ls-tree", "-rz", "--name-only", args.ref) if args.ref else git("ls-files", "-z"))
    failures = 0
    count = 0
    for raw in paths.split(b"\0"):
        if not raw:
            continue
        path = raw.decode()
        if args.ref:
            data = git("show", f"{args.ref}:{path}")
        else:
            source = ROOT / path
            if not source.exists():
                continue
            # Do not follow a tracked link into private state.
            data = str(source.readlink()).encode() if source.is_symlink() else source.read_bytes()
        count += 1
        for rule in inspect(path, data, private):
            print(f"FAIL {path}: {rule}")
            failures += 1
    print(f"Scanned {count} tracked files; {failures} findings; private binding {'loaded' if private else 'not loaded'}.")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.CalledProcessError):
        print("Publication check could not complete; inspect the repository and private binding locally.", file=sys.stderr)
        raise SystemExit(2)
