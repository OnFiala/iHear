from io import BytesIO

from pypdf import PdfReader

from ihear_worker.report import generate_report


def test_report_is_searchable_and_contains_method_boundaries() -> None:
    report = generate_report(
        {
            "display_name": "Synthetic Patient",
            "follow_up_date": "2026-10-01",
            "timezone": "Europe/Prague",
            "aids": {"side": "bilateral", "left": {"model": "Allure 220"}, "right": {"model": "Allure 220"}},
        },
        [{
            "id": "event-1",
            "kind": "difficult",
            "difficulty": "conversation",
            "environment": "cafe",
            "captured_at": "2026-09-11T10:00:00Z",
            "analysis": {
                "duration_seconds": 10.0,
                "rms_dbfs": -22.5,
                "peak_dbfs": -4.0,
                "quality_flags": [],
                "speech_activity": {"status": "ready", "fraction": 0.5},
                "acoustic_categories": {"status": "ready", "categories": [{"label": "Speech", "score": 0.8}]},
            },
            "interpretation_status": "ready",
            "interpretation": {
                "summary": "Listening was difficult in this recorded context.",
                "observations": ["Speech was present."],
                "tip_ids": ["quieter_place"],
                "limitations": ["This is not a calibrated hearing measurement."],
            },
        }],
        input_revision=7,
    )
    reader = PdfReader(BytesIO(report))
    text = " ".join("\n".join(page.extract_text() or "" for page in reader.pages).split())
    assert len(reader.pages) >= 2
    assert "Synthetic Patient" in text
    assert "Illustrative demo only. Use synthetic profiles." in text
    assert "Clinical interpretation belongs to the clinician" in text
    assert "No transcription or speaker identification" in text
    assert APPROVED_TIP_TEXT in text
    assert "This is not a calibrated hearing measurement" in text
    assert "-22.5 dBFS" in text
    assert "Follow-up: 2026-10-01" in text
    assert "Timezone: Europe/Prague" in text
    assert "Captured 2026-09-11 12:00 CEST" in text
    assert "Hearing aids: bilateral" in text
    assert "Moment 1" in text
    method_pages = [page.extract_text() or "" for page in reader.pages if "Method notes" in (page.extract_text() or "")]
    assert len(method_pages) == 1
    assert "No transcription or speaker identification" in " ".join(method_pages[0].split())


def test_silent_report_has_no_fabricated_measurement_or_estimate() -> None:
    report = generate_report(
        {
            "display_name": "Synthetic Silent Patient",
            "follow_up_date": "2026-10-01",
            "timezone": "Europe/Prague",
            "aids": {},
        },
        [{
            "id": "silent-event",
            "kind": "difficult",
            "captured_at": "unparseable-capture-time",
            "analysis": {
                "rms_dbfs": None,
                "peak_dbfs": None,
                "acoustic_categories": {
                    "status": "ready",
                    "categories": [{"label": "Unknown sound"}],
                },
            },
        }],
        input_revision=0,
    )

    reader = PdfReader(BytesIO(report))
    text = " ".join("\n".join(page.extract_text() or "" for page in reader.pages).split())

    assert "No measured RMS dBFS values are available for this report." in text
    assert "No values" not in text
    assert "0.0 dBFS" not in text
    assert "None / None dBFS" not in text
    assert "unavailable / unavailable dBFS" in text
    assert "Unknown sound (score unavailable)" in text
    assert "Unknown sound (0.00)" not in text
    assert "Captured unparseable-capture-time" in text


APPROVED_TIP_TEXT = "If you can, move to a quieter place."
