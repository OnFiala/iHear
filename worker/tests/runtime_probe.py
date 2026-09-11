"""Manual CPU/model evidence probe. It generates samples in memory and writes no audio file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import resource
import time

import numpy as np

from ihear_worker.models import ModelSuite


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("/app/config/models.json"))
    parser.add_argument("--model-dir", type=Path, default=Path("/models"))
    args = parser.parse_args()

    sample_rate = 16_000
    seconds = 10
    time_axis = np.arange(sample_rate * seconds, dtype=np.float32) / sample_rate
    waveform = (0.08 * np.sin(2 * np.pi * 440 * time_axis)).astype(np.float32)
    waveform[:sample_rate] = 0

    started = time.perf_counter()
    suite = ModelSuite(args.manifest, args.model_dir)
    speech, categories = suite.infer(waveform)
    cold_seconds = time.perf_counter() - started
    warm_started = time.perf_counter()
    suite.infer(waveform)
    warm_seconds = time.perf_counter() - warm_started
    maximum_rss_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(json.dumps({
        "architecture": __import__("platform").machine(),
        "duration_seconds": seconds,
        "silero_status": speech.get("status"),
        "silero_fraction": speech.get("fraction"),
        "yamnet_status": categories.get("status"),
        "yamnet_top_category": (categories.get("categories") or [{}])[0].get("label"),
        "cold_load_and_inference_seconds": round(cold_seconds, 3),
        "warm_inference_seconds": round(warm_seconds, 3),
        "maximum_rss_mib": round(maximum_rss_mib, 1),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
