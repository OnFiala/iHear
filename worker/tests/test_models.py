from types import SimpleNamespace

import numpy as np
import pytest

from ihear_worker.models import SileroVad, Yamnet


class _FakeVadSession:
    def __init__(self, probabilities: list[float]) -> None:
        self.calls = 0
        self.probabilities = probabilities

    def run(self, _outputs, inputs):
        probability = self.probabilities[self.calls]
        self.calls += 1
        return np.asarray([[probability]], dtype=np.float32), inputs["state"]


def test_silero_discards_padding_from_exact_one_second_weighting() -> None:
    vad = SileroVad.__new__(SileroVad)
    vad._session = _FakeVadSession([0.1] * 31 + [0.9])
    result = vad.speech_activity(np.zeros(16_000, dtype=np.float32))
    assert result["aggregation"] == "valid-duration-weighted"
    assert result["fraction"] == pytest.approx(0.008)
    assert result["mean_probability"] == pytest.approx(0.1064)
    assert len(result["windows"]) == 1
    assert result["windows"][0]["end_seconds"] == 1.0
    assert result["windows"][0]["active_fraction"] == pytest.approx(0.008)
    assert result["windows"][0]["mean_probability"] == pytest.approx(0.1064)


def test_silero_splits_a_frame_at_one_second_boundary_by_overlap() -> None:
    vad = SileroVad.__new__(SileroVad)
    vad._session = _FakeVadSession([0.1] * 31 + [0.9] + [0.1] * 15)
    result = vad.speech_activity(np.zeros(24_000, dtype=np.float32))
    assert result["fraction"] == pytest.approx(0.021333)
    assert len(result["windows"]) == 2
    assert result["windows"][0]["active_fraction"] == pytest.approx(0.008)
    assert result["windows"][0]["mean_probability"] == pytest.approx(0.1064)
    assert result["windows"][1]["end_seconds"] == 1.5
    assert result["windows"][1]["active_fraction"] == pytest.approx(0.048)
    assert result["windows"][1]["mean_probability"] == pytest.approx(0.1384)


def test_yamnet_keeps_mean_scores_and_real_frame_outputs_distinct() -> None:
    yamnet = Yamnet.__new__(Yamnet)
    scores = np.asarray([[0.9, 0.2, 0.1], [0.2, 0.8, 0.3]], dtype=np.float32)
    yamnet._model = lambda _waveform: (scores, None, None)
    yamnet._tf = SimpleNamespace(reduce_mean=lambda values, axis: np.mean(values, axis=axis))
    yamnet._labels = ["Speech", "Music", "Television"]
    result = yamnet.classify(np.zeros(24_000, dtype=np.float32), limit=3)
    assert result["aggregation"] == "mean_across_model_frames"
    assert result["categories"][0]["label"] == "Speech"
    assert [window["categories"][0]["label"] for window in result["windows"]] == [
        "Speech",
        "Music",
    ]
    assert result["windows"][1]["end_seconds"] == 1.44
