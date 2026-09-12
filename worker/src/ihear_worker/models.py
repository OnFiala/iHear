from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

import numpy as np


class SileroVad:
    VERSION = "6.2.1"
    SAMPLE_RATE = 16_000
    FRAME_SAMPLES = 512
    FRAME_SECONDS = FRAME_SAMPLES / SAMPLE_RATE

    def __init__(self, model_path: Path):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(model_path), sess_options=options, providers=["CPUExecutionProvider"]
        )

    def speech_activity(self, waveform_16khz: np.ndarray) -> dict[str, Any]:
        state = np.zeros((2, 1, 128), dtype=np.float32)
        context = np.zeros((1, 64), dtype=np.float32)
        probabilities: list[float] = []
        valid_sample_count = waveform_16khz.size
        remainder = (-valid_sample_count) % self.FRAME_SAMPLES
        waveform = np.pad(waveform_16khz, (0, remainder)) if remainder else waveform_16khz
        for offset in range(0, waveform.size, self.FRAME_SAMPLES):
            frame = waveform[offset : offset + self.FRAME_SAMPLES][None, :]
            model_input = np.concatenate((context, frame), axis=1).astype(np.float32, copy=False)
            output, state = self._session.run(
                None,
                {"input": model_input, "state": state, "sr": np.asarray(16000, dtype=np.int64)},
            )
            probabilities.append(float(np.asarray(output).reshape(-1)[0]))
            context = model_input[:, -64:]
        probability_values = np.asarray(probabilities, dtype=np.float64)
        active = probability_values >= 0.5
        frame_starts = np.arange(probability_values.size) * self.FRAME_SAMPLES
        valid_frame_samples = np.minimum(
            self.FRAME_SAMPLES,
            np.maximum(0, valid_sample_count - frame_starts),
        ).astype(np.float64)
        total_valid_samples = float(np.sum(valid_frame_samples))
        duration_seconds = valid_sample_count / self.SAMPLE_RATE
        windows: list[dict[str, float]] = []
        for second in range(int(np.ceil(duration_seconds))):
            window_start = second * self.SAMPLE_RATE
            window_end = min(valid_sample_count, (second + 1) * self.SAMPLE_RATE)
            frame_ends = np.minimum(frame_starts + self.FRAME_SAMPLES, valid_sample_count)
            overlaps = np.maximum(
                0,
                np.minimum(frame_ends, window_end) - np.maximum(frame_starts, window_start),
            ).astype(np.float64)
            overlap_total = float(np.sum(overlaps))
            if overlap_total <= 0:
                continue
            windows.append({
                "start_seconds": round(float(second), 3),
                "end_seconds": round(min(float(second + 1), duration_seconds), 3),
                "active_fraction": round(float(np.sum(overlaps * active) / overlap_total), 6),
                "mean_probability": round(
                    float(np.sum(overlaps * probability_values) / overlap_total), 6
                ),
            })
        return {
            "status": "ready",
            "fraction": round(
                float(np.sum(valid_frame_samples * active) / total_valid_samples)
                if total_valid_samples else 0.0,
                6,
            ),
            "mean_probability": round(
                float(np.sum(valid_frame_samples * probability_values) / total_valid_samples)
                if total_valid_samples else 0.0,
                6,
            ),
            "threshold": 0.5,
            "model": "silero-vad",
            "version": self.VERSION,
            "sample_rate": self.SAMPLE_RATE,
            "aggregation": "valid-duration-weighted",
            "windows": windows,
        }


class Yamnet:
    VERSION = "1"
    PATCH_WINDOW_SECONDS = 0.96
    PATCH_HOP_SECONDS = 0.48

    def __init__(self, model_dir: Path):
        os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
        import tensorflow as tf

        self._tf = tf
        self._model = tf.saved_model.load(str(model_dir))
        class_map = model_dir / "assets" / "yamnet_class_map.csv"
        with class_map.open(newline="", encoding="utf-8") as stream:
            self._labels = [row["display_name"] for row in csv.DictReader(stream)]

    def classify(self, waveform_16khz: np.ndarray, limit: int = 5) -> dict[str, Any]:
        scores, _embeddings, _spectrogram = self._model(waveform_16khz)
        frame_scores = np.asarray(scores)
        mean_scores = np.asarray(self._tf.reduce_mean(scores, axis=0))
        indices = np.argsort(mean_scores)[::-1][:limit]
        duration_seconds = waveform_16khz.size / 16_000
        windows = []
        for frame_index, values in enumerate(frame_scores):
            start = frame_index * self.PATCH_HOP_SECONDS
            if start >= duration_seconds:
                break
            frame_indices = np.argsort(values)[::-1][:3]
            windows.append({
                "start_seconds": round(start, 3),
                "end_seconds": round(min(duration_seconds, start + self.PATCH_WINDOW_SECONDS), 3),
                "categories": [
                    {"label": self._labels[int(index)], "score": round(float(values[index]), 6)}
                    for index in frame_indices
                ],
            })
        return {
            "status": "ready",
            "categories": [
                {"label": self._labels[int(index)], "score": round(float(mean_scores[index]), 6)}
                for index in indices
            ],
            "model": "YAMNet",
            "version": self.VERSION,
            "sample_rate": 16000,
            "aggregation": "mean_across_model_frames",
            "frame_window_seconds": self.PATCH_WINDOW_SECONDS,
            "frame_hop_seconds": self.PATCH_HOP_SECONDS,
            "windows": windows,
        }


class ModelSuite:
    def __init__(self, manifest_path: Path, model_dir: Path):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self._manifest = manifest
        self._model_dir = model_dir
        self._silero: SileroVad | None = None
        self._yamnet: Yamnet | None = None

    def _path(self, name: str) -> Path:
        return self._model_dir / self._manifest["models"][name]["path"]

    def infer(self, waveform_16khz: np.ndarray) -> tuple[dict[str, Any], dict[str, Any]]:
        speech: dict[str, Any]
        categories: dict[str, Any]
        try:
            self._silero = self._silero or SileroVad(self._path("silero_vad"))
            speech = self._silero.speech_activity(waveform_16khz)
        except Exception as exc:
            speech = {"status": "unavailable", "error": _bounded_error(exc), "model": "silero-vad"}
        try:
            self._yamnet = self._yamnet or Yamnet(self._path("yamnet"))
            categories = self._yamnet.classify(waveform_16khz)
        except Exception as exc:
            categories = {"status": "unavailable", "error": _bounded_error(exc), "model": "YAMNet"}
        return speech, categories


def _bounded_error(error: Exception) -> str:
    text = str(error).replace("\n", " ").strip()
    return f"{type(error).__name__}: {text}"[:240]
