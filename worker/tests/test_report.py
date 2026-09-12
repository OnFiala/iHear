from io import BytesIO
from copy import deepcopy

import pytest

from pypdf import PdfReader

from ihear_worker.report import generate_report


def _text(report: bytes) -> tuple[PdfReader, str]:
    reader = PdfReader(BytesIO(report))
    text = " ".join("\n".join(page.extract_text() or "" for page in reader.pages).split())
    return reader, text


@pytest.mark.parametrize("extra_event", [False, True])
def test_report_is_concise_chronological_and_preserves_clinical_evidence_boundaries(extra_event: bool) -> None:
    def render(patient, events, input_revision):
        if extra_event:
            third = deepcopy(events[0])
            third["id"] = "third-event"
            events.append(third)
        return generate_report(patient, events, input_revision)

    report = render(
        {
            "display_name": "Synthetic Patient",
            "follow_up_date": "2026-10-01",
            "timezone": "Europe/Prague",
            "audiogram": {
                "frequencies": [250, 500],
                "left": [20, 30],
                "right": [25, 35],
            },
            "aids": {
                "side": "bilateral",
                "left": {"model": "Allure 220", "tier": "standard"},
                "right": {"model": "Allure 220", "tier": "standard"},
            },
        },
        [
            {
                "id": "later-event",
                "kind": "difficult",
                "difficulty": "Later reported context",
                "environment": "cafe",
                "captured_at": "2026-09-11T10:00:00Z",
                "analysis": {
                    "duration_seconds": 10.0,
                    "sample_rate": 48000,
                    "rms_dbfs": -22.5,
                    "peak_dbfs": -4.0,
                    "clipping_fraction": 0.01,
                    "spectral_centroid_hz": 1800.0,
                    "quality_flags": ["clipping"],
                    "bands": [{"low_hz": 250, "high_hz": 500, "relative_energy": 0.25}],
                    "speech_activity": {"status": "ready", "fraction": 0.5, "version": "6.2.1"},
                    "acoustic_categories": {
                        "status": "ready",
                        "version": "1",
                        "categories": [{"label": "Speech", "score": 0.8}],
                    },
                },
                "interpretation_status": "ready",
                "interpretation": {
                    "summary": "Listening was difficult in this recorded context.",
                    "observations": ["Speech was present."],
                    "tip_ids": ["quieter_place"],
                    "limitations": ["This is not a calibrated hearing measurement."],
                },
            },
            {
                "id": "earlier-event",
                "kind": "understood",
                "difficulty": "Earlier reported context",
                "environment": "quiet_room",
                "captured_at": "2026-09-10T09:00:00Z",
                "analysis": {
                    "duration_seconds": 8.0,
                    "sample_rate": 48000,
                    "rms_dbfs": -30.0,
                    "peak_dbfs": -8.0,
                    "clipping_fraction": 0.0,
                    "spectral_centroid_hz": 1200.0,
                    "quality_flags": [],
                    "bands": [{"low_hz": 80, "high_hz": 250, "relative_energy": 0.4}],
                    "speech_activity": {"status": "ready", "fraction": 0.6},
                    "acoustic_categories": {
                        "status": "ready",
                        "categories": [{"label": "Speech", "score": 0.9}],
                    },
                },
                "interpretation_status": "unavailable",
                "interpretation": None,
            },
        ],
        input_revision=7,
    )
    reader, text = _text(report)

    assert len(reader.pages) >= 2
    for page in reader.pages:
        page_text = page.extract_text() or ""
        assert len(page_text) > 100, "No footer-only page may precede the appendix."
        assert not page_text.rstrip().splitlines()[-1].startswith("Moment "), "A moment heading must stay with its evidence."
    assert "Listening report" in text
    assert "Synthetic Patient" in text
    assert "10 Sep - 11 Sep 2026" in text
    assert "Follow-up 2026-10-01" in text
    assert "Clinic timezone Europe/Prague" in text
    assert "Illustrative demo only. Use synthetic profiles." in text
    assert "Phone audio measurements are uncalibrated and are not a hearing test" in text
    assert "Clinical interpretation belongs to the clinician" in text
    assert text.index("Earlier reported context") < text.index("Later reported context")
    assert "10 Sep 2026, 11:00 CEST" in text
    assert "11 Sep 2026, 12:00 CEST" in text
    assert "RMS -22.5 dBFS" in text
    assert "Sample rate 48000 Hz" in text
    assert "Spectral centroid 1800 Hz" in text
    assert "250-500 Hz 25.0%" in text
    assert "Silero speech activity: Ready" in text
    assert "YAMNet acoustic labels: Ready" in text
    assert "Clinician-entered synthetic audiogram" in text
    assert "250 Hz" in text
    assert "20 dB HL" in text
    assert "25 dB HL" in text
    assert "Listening was difficult in this recorded context." in text
    assert APPROVED_TIP_TEXT in text
    assert "This is not a calibrated hearing measurement." in text
    assert "Interpretation status: Unavailable" in text
    assert "No transcription or speaker identification" in text


def test_incomplete_report_keeps_unavailable_measurements_and_interpretation_visible() -> None:
    report = generate_report(
        {
            "display_name": "Synthetic Silent Patient",
            "follow_up_date": "2026-10-01",
            "timezone": "Europe/Prague",
            "audiogram": {"frequencies": [250, 500], "left": [20], "right": []},
            "aids": {},
        },
        [{
            "id": "silent-event",
            "kind": "difficult",
            "captured_at": "unparseable-capture-time",
            "analysis": {
                "rms_dbfs": None,
                "peak_dbfs": None,
                "speech_activity": {"status": "unavailable", "error": "model missing"},
                "acoustic_categories": {
                    "status": "ready",
                    "categories": [{"label": "Unknown sound"}],
                },
            },
            "interpretation_status": "unavailable",
            "interpretation": None,
        }],
        input_revision=0,
    )
    _, text = _text(report)

    assert "No measured RMS dBFS values are available for this report." in text
    assert "RMS unavailable" in text
    assert "peak unavailable" in text
    assert "Unknown sound (score unavailable)" in text
    assert "Silero speech activity: Unavailable | error: model missing" in text
    assert "Captured" not in text
    assert "unparseable-capture-time" in text
    assert "500 Hz" in text
    assert "Unavailable" in text
    assert "Interpretation status: Unavailable" in text
    assert "AI interpretation" not in text
    assert "No values" not in text
    assert "0.0 dBFS" not in text
    assert "None / None dBFS" not in text
    assert "Unknown sound (0.00)" not in text


APPROVED_TIP_TEXT = "If you can, move to a quieter place."
