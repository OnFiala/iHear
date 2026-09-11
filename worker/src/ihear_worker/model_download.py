from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
from typing import Any

import httpx


class ModelInstallError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if target != root and root not in target.parents:
            raise ModelInstallError(f"Unsafe path in model archive: {member.name}")
        if member.issym() or member.islnk():
            raise ModelInstallError(f"Links are not permitted in model archive: {member.name}")
    archive.extractall(destination, filter="data")


def install_models(manifest_path: Path, model_dir: Path) -> dict[str, Path]:
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    installed: dict[str, Path] = {}
    model_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=120.0) as client:
        for name, spec in manifest["models"].items():
            destination = model_dir / spec["path"]
            ready_path = destination / "saved_model.pb" if spec["format"].endswith("tar_gz") else destination
            if ready_path.exists():
                installed[name] = destination
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=model_dir, delete=False) as temporary:
                temporary_path = Path(temporary.name)
                with client.stream("GET", spec["url"]) as response:
                    response.raise_for_status()
                    for chunk in response.iter_bytes(1024 * 1024):
                        temporary.write(chunk)
            try:
                actual = _sha256(temporary_path)
                if actual != spec["sha256"]:
                    raise ModelInstallError(
                        f"Checksum mismatch for {name}: expected {spec['sha256']}, got {actual}"
                    )
                if spec["format"].endswith("tar_gz"):
                    staging = destination.with_name(destination.name + ".staging")
                    if staging.exists():
                        shutil.rmtree(staging)
                    staging.mkdir(parents=True)
                    with tarfile.open(temporary_path, "r:gz") as archive:
                        _safe_extract(archive, staging)
                    staging.replace(destination)
                else:
                    temporary_path.replace(destination)
                installed[name] = destination
            finally:
                temporary_path.unlink(missing_ok=True)
    return installed


def main() -> None:
    parser = argparse.ArgumentParser(description="Install verified iHear model artifacts")
    parser.add_argument("--manifest", type=Path, default=Path("/app/config/models.json"))
    parser.add_argument("--model-dir", type=Path, default=Path("/models"))
    args = parser.parse_args()
    for name, path in install_models(args.manifest, args.model_dir).items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
