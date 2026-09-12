"""Fail-closed validation for the ignored dedicated-runtime identity file."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import stat


MAX_IDENTITY_BYTES = 4096


def validate_runtime_identity(
    path: Path,
    *,
    expected_uid: int,
    current_hostname: str | None = None,
) -> None:
    """Validate the private runtime identity without returning or logging it."""
    try:
        metadata = path.lstat()
    except OSError as error:
        raise RuntimeError("The private runtime identity file is missing or unreadable.") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError("The private runtime identity must be a regular non-symlink file.")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise RuntimeError("The private runtime identity file must have mode 0600.")
    if metadata.st_uid != expected_uid:
        raise RuntimeError("The private runtime identity file has the wrong owner.")
    if metadata.st_size <= 0 or metadata.st_size > MAX_IDENTITY_BYTES:
        raise RuntimeError("The private runtime identity file has an invalid size.")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise RuntimeError("The private runtime identity file could not be opened safely.") from error
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_uid != expected_uid
            or (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino)
        ):
            raise RuntimeError("The private runtime identity changed during validation.")
        raw = os.read(descriptor, MAX_IDENTITY_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(raw) > MAX_IDENTITY_BYTES:
        raise RuntimeError("The private runtime identity file has an invalid size.")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("The private runtime identity file is invalid.") from error
    if not isinstance(payload, dict) or set(payload) != {"hostname", "schema_version"}:
        raise RuntimeError("The private runtime identity schema is invalid.")
    hostname = payload.get("hostname")
    if (
        payload.get("schema_version") != 1
        or not isinstance(hostname, str)
        or not hostname
        or len(hostname) > 255
        or any(character.isspace() for character in hostname)
    ):
        raise RuntimeError("The private runtime identity schema is invalid.")
    observed = socket.gethostname() if current_hostname is None else current_hostname
    if hostname != observed:
        raise RuntimeError("The private runtime identity does not match this host.")
