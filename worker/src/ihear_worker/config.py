from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    supabase_url: str
    supabase_service_role_key: str
    openai_api_key: str | None
    audio_bucket: str = "ihear-audio"
    report_bucket: str = "ihear-reports"
    queue_name: str = "ihear_jobs"
    pipeline_version: int = 1
    report_version: int = 2
    clinic_timezone: str = "Europe/Prague"
    model_manifest: Path = Path("/app/config/models.json")
    device_capabilities: Path = Path("/app/config/device-capabilities.json")
    model_dir: Path = Path("/models")
    worker_id: str = "ihear-worker"
    lease_seconds: int = 120
    poll_seconds: float = 2.0

    @classmethod
    def from_env(cls) -> "Settings":
        required = ("DATABASE_URL", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
        missing = [name for name in required if not os.getenv(name)]
        if missing:
            raise RuntimeError(f"Missing required worker configuration: {', '.join(missing)}")
        fixed_values = {
            "ASTRA_MODEL": "gpt-6-astra",
            "ASTRA_REASONING_EFFORT": "low",
            "WORKER_CONCURRENCY": "1",
        }
        mismatches = [
            f"{name} must be {expected!r}"
            for name, expected in fixed_values.items()
            if os.getenv(name, expected) != expected
        ]
        if mismatches:
            raise RuntimeError("Unsupported worker configuration: " + "; ".join(mismatches))
        return cls(
            database_url=os.environ["DATABASE_URL"],
            supabase_url=os.environ["SUPABASE_URL"].rstrip("/"),
            supabase_service_role_key=os.environ["SUPABASE_SERVICE_ROLE_KEY"],
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            audio_bucket=os.getenv("AUDIO_BUCKET", "ihear-audio"),
            report_bucket=os.getenv("REPORT_BUCKET", "ihear-reports"),
            queue_name=os.getenv("QUEUE_NAME", "ihear_jobs"),
            pipeline_version=int(os.getenv("PIPELINE_VERSION", "1")),
            report_version=int(os.getenv("REPORT_VERSION", "2")),
            clinic_timezone=os.getenv("CLINIC_TIMEZONE", "Europe/Prague"),
            model_manifest=Path(os.getenv("MODEL_MANIFEST", "/app/config/models.json")),
            device_capabilities=Path(os.getenv("DEVICE_CAPABILITIES", "/app/config/device-capabilities.json")),
            model_dir=Path(os.getenv("MODEL_DIR", "/models")),
            worker_id=os.getenv("WORKER_ID", f"ihear-worker-{os.getpid()}"),
            lease_seconds=int(os.getenv("JOB_LEASE_SECONDS", "120")),
            poll_seconds=float(os.getenv("JOB_POLL_SECONDS", "2")),
        )
