from io import BytesIO

import numpy as np
import pytest
from scipy.io import wavfile

from ihear_worker.dsp import AudioValidationError, analyze_deterministic, decode_pcm16_mono_wav


def make_wav(samples: np.ndarray, sample_rate: int = 44_100) -> bytes:
    stream = BytesIO()
    wavfile.write(stream, sample_rate, samples.astype(np.int16))
    return stream.getvalue()


def test_native_rate_stft_finds_known_mid_band_tone() -> None:
    sample_rate = 44_100
    time = np.arange(sample_rate * 2) / sample_rate
    pcm = np.round(np.sin(2 * np.pi * 1_500 * time) * 12_000).astype(np.int16)
    result = analyze_deterministic(decode_pcm16_mono_wav(make_wav(pcm, sample_rate)))
    dominant = max(result["bands"], key=lambda band: band["relative_energy"])
    assert result["sample_rate"] == sample_rate
    assert dominant["low_hz"] == 1_000
    assert dominant["high_hz"] == 2_000
    assert dominant["relative_energy"] > 0.95
    assert 1_450 < result["spectral_centroid_hz"] < 1_550


def test_silence_and_clipping_are_reported() -> None:
    silence = analyze_deterministic(decode_pcm16_mono_wav(make_wav(np.zeros(16_000), 16_000)))
    assert silence["silent"] is True
    assert silence["rms_dbfs"] is None
    assert "silence" in silence["quality_flags"]

    clipped_pcm = np.resize(np.array([-32768, 32767], dtype=np.int16), 16_000)
    clipped = analyze_deterministic(decode_pcm16_mono_wav(make_wav(clipped_pcm, 16_000)))
    assert clipped["clipping_fraction"] == 1.0
    assert "clipping" in clipped["quality_flags"]


def test_duration_and_pcm_contract_are_enforced() -> None:
    too_long = np.zeros(int(16_000 * 10.2), dtype=np.int16)
    with pytest.raises(AudioValidationError, match="10.1"):
        decode_pcm16_mono_wav(make_wav(too_long, 16_000))

    stream = BytesIO()
    wavfile.write(stream, 16_000, np.zeros(16_000, dtype=np.float32))
    with pytest.raises(AudioValidationError, match="16-bit PCM"):
        decode_pcm16_mono_wav(stream.getvalue())
