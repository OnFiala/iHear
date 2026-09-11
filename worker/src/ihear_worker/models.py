from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

import numpy as np


class SileroVad:
    VERSION = "6.2.1"

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
        remainder = (-waveform_16khz.size) % 512
        waveform = np.pad(waveform_16khz, (0, remainder)) if remainder else waveform_16khz
        for offset in range(0, waveform.size, 512):
            frame = waveform[offset : offset + 512][None, :]
            model_input = np.concatenate((context, frame), axis=1).astype(np.float32, copy=False)
            output, state = self._session.run(
                None,
                {"input": model_input, "state": state, "sr": np.asarray(16000, dtype=np.int64)},
            )
            probabilities.append(float(np.asarray(output).reshape(-1)[0]))
            context = model_input[:, -64:]
        active = np.asarray(probabilities) >= 0.5
        return {
            "status": "ready",
            "fraction": round(float(np.mean(active)) if active.size else 0.0, 6),
            "mean_probability": round(float(np.mean(probabilities)) if probabilities else 0.0, 6),
            "threshold": 0.5,
            "model": "silero-vad",
            "version": self.VERSION,
            "sample_rate": 16000,
        }


class Yamnet:
    VERSION = "1"

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
        mean_scores = np.asarray(self._tf.reduce_mean(scores, axis=0))
        indices = np.argsort(mean_scores)[::-1][:limit]
        return {
            "status": "ready",
            "categories": [
                {"label": self._labels[int(index)], "score": round(float(mean_scores[index]), 6)}
                for index in indices
            ],
            "model": "YAMNet",
            "version": self.VERSION,
            "sample_rate": 16000,
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
