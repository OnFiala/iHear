from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import math
from typing import Any

import numpy as np
from scipy import signal
from scipy.io import wavfile


MAX_AUDIO_BYTES = 2_202_000
MAX_DURATION_SECONDS = 10.1
BANDS_HZ = ((80, 250), (250, 500), (500, 1000), (1000, 2000), (2000, 4000), (4000, 8000))


class AudioValidationError(ValueError):
    pass


@dataclass(frozen=True)
class AudioBuffer:
    sample_rate: int
    pcm: np.ndarray
    samples: np.ndarray

    @property
    def duration_seconds(self) -> float:
        return float(self.samples.size / self.sample_rate)


def decode_pcm16_mono_wav(data: bytes) -> AudioBuffer:
    if len(data) > MAX_AUDIO_BYTES:
        raise AudioValidationError("Audio exceeds the 2,202,000-byte limit")
    try:
        sample_rate, pcm = wavfile.read(BytesIO(data), mmap=False)
    except Exception as exc:
        raise AudioValidationError("Audio is not a valid WAV file") from exc
    if not isinstance(sample_rate, (int, np.integer)) or not 8_000 <= int(sample_rate) <= 96_000:
        raise AudioValidationError("WAV sample rate must be between 8 kHz and 96 kHz")
    if pcm.dtype != np.int16:
        raise AudioValidationError("WAV must contain signed 16-bit PCM")
    if pcm.ndim != 1:
        raise AudioValidationError("WAV must be mono")
    if pcm.size == 0:
        raise AudioValidationError("WAV contains no samples")
    samples = pcm.astype(np.float32) / 32768.0
    result = AudioBuffer(int(sample_rate), pcm, samples)
    if result.duration_seconds > MAX_DURATION_SECONDS:
        raise AudioValidationError("Audio exceeds the 10.1 second limit")
    return result


def _dbfs(value: float) -> float | None:
    if value <= np.finfo(np.float32).eps:
        return None
    return round(20.0 * math.log10(value), 3)


def _stft_power(audio: AudioBuffer) -> tuple[np.ndarray, np.ndarray]:
    target = max(64, int(round(audio.sample_rate * 0.025)))
    nperseg = min(audio.samples.size, 1 << int(math.ceil(math.log2(target))))
    if nperseg < 2:
        return np.array([0.0]), np.zeros((1, 1), dtype=np.float64)
    overlap = min(nperseg - 1, int(round(nperseg * 0.5)))
    frequencies, _, zxx = signal.stft(
        audio.samples,
        fs=audio.sample_rate,
        window="hann",
        nperseg=nperseg,
        noverlap=overlap,
        detrend=False,
        boundary=None,
        padded=False,
    )
    return frequencies, np.square(np.abs(zxx), dtype=np.float64)


def analyze_deterministic(audio: AudioBuffer) -> dict[str, Any]:
    samples64 = audio.samples.astype(np.float64, copy=False)
    rms = float(np.sqrt(np.mean(np.square(samples64))))
    peak = float(np.max(np.abs(samples64)))
    clipping_fraction = float(np.mean(np.abs(audio.pcm.astype(np.int32)) >= 32767))
    rms_dbfs = _dbfs(rms)
    silent = rms_dbfs is None or rms_dbfs < -60.0

    frequencies, power = _stft_power(audio)
    mean_power = np.mean(power, axis=1) if power.size else np.zeros_like(frequencies)
    total_power = float(np.sum(mean_power[frequencies >= 20]))
    nyquist = audio.sample_rate / 2.0
    bands: list[dict[str, int | float]] = []
    for low, high in BANDS_HZ:
        upper = min(float(high), nyquist)
        mask = (frequencies >= low) & (frequencies < upper)
        energy = float(np.sum(mean_power[mask])) if upper > low else 0.0
        bands.append({
            "low_hz": low,
            "high_hz": high,
            "relative_energy": round(energy / total_power, 6) if total_power > 0 else 0.0,
        })

    weighted = float(np.sum(frequencies * mean_power))
    centroid = weighted / float(np.sum(mean_power)) if float(np.sum(mean_power)) > 0 else 0.0
    flags: list[str] = []
    if silent:
        flags.append("silence")
    if clipping_fraction >= 0.01:
        flags.append("clipping")
    if audio.duration_seconds < 0.5:
        flags.append("too_short")
    if rms_dbfs is not None and rms_dbfs < -45.0:
        flags.append("very_quiet")

    return {
        "duration_seconds": round(audio.duration_seconds, 4),
        "sample_rate": audio.sample_rate,
        "rms_dbfs": rms_dbfs,
        "peak_dbfs": _dbfs(peak),
        "clipping_fraction": round(clipping_fraction, 6),
        "silent": silent,
        "quality_flags": flags,
        "bands": bands,
        "spectral_centroid_hz": round(centroid, 2),
    }


def resample_for_models(audio: AudioBuffer, target_rate: int = 16_000) -> np.ndarray:
    if audio.sample_rate == target_rate:
        return np.ascontiguousarray(audio.samples, dtype=np.float32)
    divisor = math.gcd(audio.sample_rate, target_rate)
    output = signal.resample_poly(
        audio.samples,
        target_rate // divisor,
        audio.sample_rate // divisor,
    )
    return np.ascontiguousarray(output, dtype=np.float32)


def interpretation_is_ambiguous(analysis: dict[str, Any]) -> bool:
    speech = analysis.get("speech_activity") or {}
    return bool(
        analysis.get("silent")
        or analysis.get("duration_seconds", 0) < 1.0
        or analysis.get("clipping_fraction", 0) >= 0.10
        or speech.get("status") != "ready"
        or speech.get("fraction", 0) < 0.05
    )
