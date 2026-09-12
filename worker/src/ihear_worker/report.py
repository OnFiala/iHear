from __future__ import annotations

from collections import Counter
from datetime import datetime
from io import BytesIO
import math
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from .astra import APPROVED_TIPS


INK = colors.HexColor("#101828")
COBALT = colors.HexColor("#0B57FF")
COBALT_DARK = colors.HexColor("#083AA9")
BLUE_PALE = colors.HexColor("#EEF4FF")
YELLOW_PALE = colors.HexColor("#FFF3C7")
BORDER = colors.HexColor("#D7E0F2")
MUTED = colors.HexColor("#536686")
SOFT = colors.HexColor("#F7F9FC")


def _page_chrome(canvas: Any, document: Any) -> None:
    canvas.saveState()
    canvas.setStrokeColor(COBALT)
    canvas.setLineWidth(1.2)
    canvas.line(18 * mm, 15 * mm, A4[0] - 18 * mm, 15 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 9.5 * mm, "Illustrative data - phone audio is not a hearing test.")
    canvas.drawRightString(A4[0] - 18 * mm, 9.5 * mm, f"Page {document.page}")
    canvas.restoreState()


def generate_report(patient: dict[str, Any], events: list[dict[str, Any]], input_revision: int) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=14 * mm,
        bottomMargin=22 * mm,
        title=f"Listening report - {patient.get('display_name', 'Patient')}",
        author="iHear",
        subject=f"Listening evidence revision {input_revision}",
    )
    styles = _styles()
    timezone_name = _bounded_display(patient.get("timezone"), 64)
    report_timezone = _timezone(timezone_name)
    timezone_label = timezone_name if report_timezone else "Not available"
    ordered_events = _ordered_events(events)
    ready = [event for event in ordered_events if isinstance(event.get("analysis"), dict)]
    counts = Counter(event.get("kind") for event in ordered_events)
    follow_up = _bounded_display(patient.get("follow_up_date"), 40) or "Not set"
    patient_name = _bounded_display(patient.get("display_name"), 120) or "Unknown patient"
    coverage = _coverage_label(ordered_events, report_timezone)

    story: list[Any] = [
        Table(
            [[
                Paragraph("iHear", styles["Brand"]),
                Paragraph(f"REPORT DATE<br/><b>{_escape(_report_date(report_timezone))}</b>", styles["HeaderMeta"]),
            ]],
            colWidths=[110 * mm, 63 * mm],
            style=TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
            ]),
        ),
        HRFlowable(width="100%", thickness=2.2, color=COBALT, spaceAfter=7 * mm),
        Paragraph("Listening report", styles["ReportTitle"]),
        Paragraph(_escape(patient_name), styles["PatientName"]),
        Paragraph(_escape(coverage), styles["DateRange"]),
        Spacer(1, 2 * mm),
        Table(
            [[
                Paragraph(f"<b>Follow-up</b><br/>{_escape(follow_up)}", styles["MetaCard"]),
                Paragraph(f"<b>Clinic timezone</b><br/>{_escape(timezone_label)}", styles["MetaCard"]),
                Paragraph(f"<b>Hearing aids</b><br/>{_escape(_aid_summary(patient.get('aids')))}", styles["MetaCard"]),
            ]],
            colWidths=[45 * mm, 49 * mm, 79 * mm],
            style=_card_style(BLUE_PALE),
        ),
        Spacer(1, 4 * mm),
        Table(
            [[Paragraph(
                "<b>Illustrative demo only. Use synthetic profiles.</b> "
                "Phone audio measurements are uncalibrated and are not a hearing test. "
                "This report is not a diagnosis and does not prescribe hearing-aid settings. "
                "Clinical interpretation belongs to the clinician.",
                styles["Caveat"],
            )]],
            colWidths=[173 * mm],
            style=_card_style(YELLOW_PALE),
        ),
        Spacer(1, 7 * mm),
        Paragraph("At a glance", styles["Section"]),
        _summary_table(len(ordered_events), counts, len(ready), styles),
    ]

    if not any(_is_number((event.get("analysis") or {}).get("rms_dbfs")) for event in ready):
        story.extend([
            Spacer(1, 3 * mm),
            Paragraph("No measured RMS dBFS values are available for this report.", styles["Notice"]),
        ])

    story.extend([Spacer(1, 7 * mm), Paragraph("Moments", styles["Section"])])
    if not ordered_events:
        story.append(Paragraph("No listening moments were recorded for this report.", styles["BodyMuted"]))
    else:
        for event_index, event in enumerate(ordered_events, 1):
            story.extend(_moment_story(event_index, event, report_timezone, styles))

    story.extend([
        PageBreak(),
        Paragraph("Technical record", styles["AppendixTitle"]),
        Paragraph(
            "Deterministic phone-audio measurements and model estimates are listed separately. "
            "They are not hearing thresholds and are not compared with the audiogram.",
            styles["BodyMuted"],
        ),
        Spacer(1, 5 * mm),
        Paragraph("Patient profile", styles["Section"]),
        Paragraph(
            f"<b>Evidence revision:</b> {input_revision} &nbsp;&nbsp; "
            f"<b>Clinic timezone:</b> {_escape(timezone_label)} &nbsp;&nbsp; "
            f"<b>Hearing aids:</b> {_escape(_aid_summary(patient.get('aids')))}",
            styles["Body"],
        ),
        Spacer(1, 3 * mm),
        Paragraph("Clinician-entered synthetic audiogram", styles["Subsection"]),
        Paragraph(
            "Hearing levels below are profile data in dB HL. They are not inferred from phone audio.",
            styles["BodyMuted"],
        ),
        Spacer(1, 2 * mm),
        _audiogram_table(patient.get("audiogram"), styles),
        Spacer(1, 6 * mm),
        Paragraph("Per-moment acoustic details", styles["Section"]),
    ])

    if not ordered_events:
        story.append(Paragraph("No acoustic details are available.", styles["BodyMuted"]))
    else:
        for event_index, event in enumerate(ordered_events, 1):
            story.extend(_technical_event_story(event_index, event, report_timezone, styles))

    story.extend([
        Spacer(1, 6 * mm),
        KeepTogether([
            Paragraph("Method and limits", styles["Section"]),
            Paragraph(
                "Frequency-band energy and spectral centroid come from native-rate STFT analysis. "
                "Speech activity is a Silero VAD estimate after resampling to 16 kHz. "
                "Acoustic labels are YAMNet estimates after resampling to 16 kHz. "
                "No transcription or speaker identification is performed.",
                styles["Body"],
            ),
        ]),
    ])
    document.build(story, onFirstPage=_page_chrome, onLaterPages=_page_chrome)
    return output.getvalue()


def _styles() -> Any:
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Brand", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=17, leading=19, textColor=INK))
    styles.add(ParagraphStyle(name="HeaderMeta", parent=styles["Normal"], fontName="Helvetica", fontSize=7.5, leading=10, textColor=MUTED, alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=25, leading=28, textColor=COBALT, alignment=TA_LEFT, spaceAfter=2 * mm))
    styles.add(ParagraphStyle(name="PatientName", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=INK))
    styles.add(ParagraphStyle(name="DateRange", parent=styles["Normal"], fontName="Helvetica", fontSize=9.5, leading=12, textColor=MUTED))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12.5, leading=15, textColor=INK, spaceBefore=0, spaceAfter=3 * mm))
    styles.add(ParagraphStyle(name="AppendixTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=21, leading=24, textColor=COBALT, alignment=TA_LEFT, spaceAfter=2 * mm))
    styles.add(ParagraphStyle(name="Subsection", parent=styles["Heading3"], keepWithNext=True, fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=INK, spaceBefore=0, spaceAfter=1 * mm))
    styles.add(ParagraphStyle(name="Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.5, leading=12, textColor=INK))
    styles.add(ParagraphStyle(name="BodyMuted", parent=styles["BodyText"], fontName="Helvetica", fontSize=8, leading=11, textColor=MUTED))
    styles.add(ParagraphStyle(name="MetaCard", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.7, leading=10.5, textColor=INK))
    styles.add(ParagraphStyle(name="Caveat", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.2, leading=11.5, textColor=INK))
    styles.add(ParagraphStyle(name="Notice", parent=styles["BodyText"], fontName="Helvetica", fontSize=8, leading=11, textColor=COBALT_DARK, leftIndent=3 * mm, borderColor=BORDER, borderWidth=0.5, borderPadding=2 * mm, backColor=BLUE_PALE))
    styles.add(ParagraphStyle(name="MomentNumber", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=13, textColor=COBALT, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name="MomentTitle", parent=styles["Normal"], fontName="Helvetica", fontSize=10, leading=13, textColor=INK))
    styles.add(ParagraphStyle(name="MomentMeta", parent=styles["Normal"], fontName="Helvetica", fontSize=7.7, leading=10.5, textColor=MUTED, alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name="MomentBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8, leading=11.5, textColor=INK))
    styles.add(ParagraphStyle(name="Interpretation", parent=styles["BodyText"], fontName="Helvetica", fontSize=8, leading=11.5, textColor=COBALT_DARK))
    return styles


def _card_style(background: colors.Color) -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), background),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3.5 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3.5 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
        ("LINEBEFORE", (1, 0), (-1, -1), 0.4, BORDER),
    ])


def _summary_table(total: int, counts: Counter[Any], analysed: int, styles: Any) -> Table:
    values = [(str(total), "Recorded"), (str(counts.get("understood", 0)), "Understood"), (str(counts.get("difficult", 0)), "Difficult"), (str(analysed), "Analysed")]
    cells = [Paragraph(f"<font size='15'><b>{value}</b></font><br/><font color='#536686'>{label}</font>", styles["MetaCard"]) for value, label in values]
    return Table([cells], colWidths=[43.25 * mm] * 4, style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SOFT), ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("LINEBEFORE", (1, 0), (-1, -1), 0.5, BORDER), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 3 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
    ]))


def _moment_story(index: int, event: dict[str, Any], timezone: ZoneInfo | None, styles: Any) -> list[Any]:
    analysis = event.get("analysis") if isinstance(event.get("analysis"), dict) else None
    header = Table([[
        Paragraph(f"{index:02d}", styles["MomentNumber"]),
        Paragraph(f"<b>{_escape(_feedback_label(event.get('kind')))}</b>", styles["MomentTitle"]),
        Paragraph(_escape(_local_timestamp(event.get("captured_at"), timezone)), styles["MomentMeta"]),
    ]], colWidths=[13 * mm, 92 * mm, 68 * mm], style=TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), BLUE_PALE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2 * mm),
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, COBALT),
    ]))
    body_rows = [[Paragraph("<b>Reported context</b>", styles["MomentBody"]), Paragraph(_escape(_reported_context(event)), styles["MomentBody"])]]
    measurements = _measurement_summary(analysis)
    estimates = _estimate_summary(analysis)
    if measurements:
        body_rows.append([Paragraph("<b>Phone-audio measurements</b>", styles["MomentBody"]), Paragraph(_escape(measurements), styles["MomentBody"])])
    elif analysis is None:
        body_rows.append([Paragraph("<b>Acoustic analysis</b>", styles["MomentBody"]), Paragraph("Not available", styles["MomentBody"])])
    if estimates:
        body_rows.append([Paragraph("<b>Model estimates</b>", styles["MomentBody"]), Paragraph(_escape(estimates), styles["MomentBody"])])
    body = Table(body_rows, colWidths=[47 * mm, 126 * mm], style=TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, -1), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.7 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.7 * mm),
    ]))
    result: list[Any] = [KeepTogether([header, body])]
    result.extend(_interpretation_story(event, styles))
    # Flowable spacing is discarded at a page boundary; a standalone Spacer
    # could consume a fresh page immediately before the appendix PageBreak.
    result[-1].spaceAfter = 3.5 * mm
    return result


def _interpretation_story(event: dict[str, Any], styles: Any) -> list[Any]:
    status = str(event.get("interpretation_status") or "").strip()
    interpretation = event.get("interpretation")
    if status == "ready" and isinstance(interpretation, dict):
        lines = []
        summary = _bounded_display(interpretation.get("summary"), 600)
        if summary:
            lines.append(summary)
        observations = _bounded_list(interpretation.get("observations"), 4, 240)
        if observations:
            lines.append("Observations: " + " | ".join(observations))
        tip_ids = interpretation.get("tip_ids") if isinstance(interpretation.get("tip_ids"), list) else []
        tips = [APPROVED_TIPS[tip_id] for tip_id in tip_ids[:3] if tip_id in APPROVED_TIPS]
        if tips:
            lines.append("Patient tips: " + " | ".join(tips))
        limitations = _bounded_list(interpretation.get("limitations"), 4, 240)
        if limitations:
            lines.append("Limitations: " + " | ".join(limitations))
        if not lines:
            lines.append("Ready interpretation contained no displayable text.")
        return [Table([[Paragraph("<b>Interpretation</b><br/>" + _escape(" ".join(lines)), styles["Interpretation"])]], colWidths=[173 * mm], style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BLUE_PALE), ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
            ("TOPPADDING", (0, 0), (-1, -1), 2 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
        ]))]
    if status:
        return [Paragraph(f"<b>Interpretation status:</b> {_escape(_humanize(status))}", styles["Interpretation"])]
    return []


def _technical_event_story(index: int, event: dict[str, Any], timezone: ZoneInfo | None, styles: Any) -> list[Any]:
    analysis = event.get("analysis") if isinstance(event.get("analysis"), dict) else None
    title = f"Moment {index:02d} - {_feedback_label(event.get('kind'))} - {_local_timestamp(event.get('captured_at'), timezone)}"
    rows: list[list[str]] = []
    if analysis is None:
        rows.append(["Analysis", "Not available"])
    else:
        rows.append(["Deterministic measurements", _measurement_detail(analysis)])
        if "quality_flags" in analysis:
            flags = analysis.get("quality_flags")
            flag_text = ", ".join(
                "Weak digital signal in this recording; environmental loudness cannot be inferred"
                if flag in {"very_quiet", "weak_digital_signal"} else _humanize(str(flag))
                for flag in flags
            ) if isinstance(flags, list) else "Unavailable"
            rows.append(["Quality flags", flag_text or "None"])
        bands = _band_summary(analysis.get("bands"))
        if bands:
            rows.append(["Relative band energy", bands])
        speech = _model_detail("Silero speech activity", analysis.get("speech_activity"), speech=True)
        if speech:
            rows.append(["Model estimate", speech])
        acoustic = _model_detail("YAMNet acoustic labels", analysis.get("acoustic_categories"), speech=False)
        if acoustic:
            rows.append(["Model estimate", acoustic])
    table_rows = [[Paragraph(f"<b>{_escape(label)}</b>", styles["BodyMuted"]), Paragraph(_escape(value), styles["Body"])] for label, value in rows]
    return [
        Paragraph(_escape(title), styles["Subsection"]),
        Table(table_rows, colWidths=[43 * mm, 130 * mm], style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (0, -1), SOFT),
            ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 2.5 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5 * mm),
            ("TOPPADDING", (0, 0), (-1, -1), 1.7 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.7 * mm),
        ])), Spacer(1, 4 * mm),
    ]


def _audiogram_table(value: Any, styles: Any) -> Any:
    rows = _audiogram_rows(value)
    if not rows:
        return Paragraph("No audiogram values were supplied.", styles["BodyMuted"])
    data = [[Paragraph("<b>Frequency</b>", styles["BodyMuted"]), Paragraph("<b>Left ear</b>", styles["BodyMuted"]), Paragraph("<b>Right ear</b>", styles["BodyMuted"])]]
    for frequency, left, right in rows:
        data.append([Paragraph(_escape(frequency), styles["Body"]), Paragraph(_escape(left), styles["Body"]), Paragraph(_escape(right), styles["Body"])])
    return Table(data, colWidths=[57.7 * mm] * 3, style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE_PALE), ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5 * mm),
    ]))


def _audiogram_rows(value: Any) -> list[tuple[str, str, str]]:
    if not isinstance(value, dict) or not isinstance(value.get("frequencies"), list) or not value["frequencies"]:
        return []
    left = value.get("left") if isinstance(value.get("left"), list) else []
    right = value.get("right") if isinstance(value.get("right"), list) else []
    rows = []
    for index, frequency in enumerate(value["frequencies"][:16]):
        rows.append((_value_with_unit(frequency, "Hz", 0), _value_with_unit(left[index] if index < len(left) else None, "dB HL", 0), _value_with_unit(right[index] if index < len(right) else None, "dB HL", 0)))
    return rows


def _measurement_summary(analysis: dict[str, Any] | None) -> str | None:
    if analysis is None:
        return None
    parts = []
    if _is_number(analysis.get("duration_seconds")):
        parts.append(f"{float(analysis['duration_seconds']):.1f} s")
    if _is_number(analysis.get("rms_dbfs")):
        parts.append(f"RMS {float(analysis['rms_dbfs']):.1f} dBFS")
    elif "rms_dbfs" in analysis:
        parts.append("RMS unavailable")
    if _is_number(analysis.get("peak_dbfs")):
        parts.append(f"peak {float(analysis['peak_dbfs']):.1f} dBFS")
    elif "peak_dbfs" in analysis:
        parts.append("peak unavailable")
    return " | ".join(parts) or None


def _measurement_detail(analysis: dict[str, Any]) -> str:
    parts = []
    definitions = [("Duration", "duration_seconds", "s", 1), ("Sample rate", "sample_rate", "Hz", 0), ("RMS", "rms_dbfs", "dBFS", 1), ("Peak", "peak_dbfs", "dBFS", 1), ("Clipping", "clipping_fraction", "%", 2), ("Spectral centroid", "spectral_centroid_hz", "Hz", 0)]
    for label, key, unit, decimals in definitions:
        value = analysis.get(key)
        if _is_number(value):
            numeric = float(value) * 100 if key == "clipping_fraction" else float(value)
            parts.append(f"{label} {numeric:.{decimals}f} {unit}")
        elif key in analysis:
            parts.append(f"{label} unavailable")
    return " | ".join(parts) or "No deterministic measurements available"


def _estimate_summary(analysis: dict[str, Any] | None) -> str | None:
    if analysis is None:
        return None
    parts = []
    speech = analysis.get("speech_activity")
    if isinstance(speech, dict) and speech.get("status") == "ready" and _is_number(speech.get("fraction")):
        parts.append(f"Silero speech activity {float(speech['fraction']):.2f}")
    categories = analysis.get("acoustic_categories")
    if isinstance(categories, dict) and isinstance(categories.get("categories"), list):
        rendered = [_category_display(item) for item in categories["categories"][:3] if isinstance(item, dict)]
        if rendered:
            parts.append("YAMNet " + ", ".join(rendered))
    return " | ".join(parts) or None


def _model_detail(label: str, value: Any, *, speech: bool) -> str | None:
    if not isinstance(value, dict):
        return None
    parts = [f"{label}: {_humanize(str(value.get('status') or 'unknown'))}"]
    if speech and _is_number(value.get("fraction")):
        parts.append(f"fraction {float(value['fraction']):.2f}")
    if not speech and isinstance(value.get("categories"), list):
        rendered = [_category_display(item) for item in value["categories"][:5] if isinstance(item, dict)]
        if rendered:
            parts.append(", ".join(rendered))
    error = _bounded_display(value.get("error"), 240)
    if error:
        parts.append(f"error: {error}")
    version = _bounded_display(value.get("version"), 80)
    if version:
        parts.append(f"version {version}")
    return " | ".join(parts)


def _band_summary(value: Any) -> str | None:
    if not isinstance(value, list):
        return None
    parts = []
    for band in value[:12]:
        if not isinstance(band, dict) or not _is_number(band.get("relative_energy")):
            continue
        low = _number_text(band.get("low_hz"), 0)
        high = _number_text(band.get("high_hz"), 0)
        if low is not None and high is not None:
            parts.append(f"{low}-{high} Hz {float(band['relative_energy']) * 100:.1f}%")
    return " | ".join(parts) or None


def _reported_context(event: dict[str, Any]) -> str:
    values = []
    difficulty = _bounded_display(event.get("difficulty"), 120)
    environment = _bounded_display(event.get("environment"), 120)
    if difficulty:
        values.append(_humanize(difficulty))
    if environment:
        values.append(_humanize(environment))
    return " | ".join(values) or "No context supplied"


def _feedback_label(value: Any) -> str:
    if value == "understood":
        return "I understood"
    if value == "difficult":
        return "I did not understand"
    return _humanize(str(value or "Unknown feedback"))


def _ordered_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = list(enumerate(events))
    indexed.sort(key=lambda item: _event_sort_key(item[1], item[0]))
    return [event for _, event in indexed]


def _event_sort_key(event: dict[str, Any], index: int) -> tuple[int, float, int]:
    parsed = _parse_timestamp(event.get("captured_at"))
    return (0, parsed.timestamp(), index) if parsed is not None else (1, 0.0, index)


def _coverage_label(events: list[dict[str, Any]], timezone: ZoneInfo | None) -> str:
    dates = []
    for event in events:
        parsed = _parse_timestamp(event.get("captured_at"))
        if parsed is not None:
            dates.append((parsed.astimezone(timezone) if timezone else parsed).date())
    if not dates:
        return "Recorded dates unavailable"
    first, last = min(dates), max(dates)
    if first == last:
        return first.strftime("%d %b %Y")
    if first.year == last.year:
        return f"{first.strftime('%d %b')} - {last.strftime('%d %b %Y')}"
    return f"{first.strftime('%d %b %Y')} - {last.strftime('%d %b %Y')}"


def _report_date(timezone: ZoneInfo | None) -> str:
    return datetime.now(timezone).strftime("%d %b %Y") if timezone else "Not available"


def _local_timestamp(value: Any, timezone: ZoneInfo | None) -> str:
    original = str(value or "unknown")
    parsed = _parse_timestamp(value)
    if timezone is None or parsed is None:
        return original
    return parsed.astimezone(timezone).strftime("%d %b %Y, %H:%M %Z")


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _aid_summary(value: Any) -> str:
    if not isinstance(value, dict):
        return "Not supplied"
    side = _bounded_display(value.get("side"), 24)
    models = []
    for channel in ("left", "right"):
        device = value.get(channel)
        if isinstance(device, dict):
            model = _bounded_display(device.get("model"), 60)
            tier = _bounded_display(device.get("tier"), 40)
            detail = " ".join(filter(None, [model, tier]))
            if detail:
                models.append(f"{channel}: {detail}")
    return "; ".join(filter(None, [side, *models])) or "Not supplied"


def _category_display(item: dict[str, Any]) -> str:
    label = _bounded_display(item.get("label"), 80) or "Unlabelled category"
    score = item.get("score")
    return f"{label} ({float(score):.2f})" if _is_number(score) else f"{label} (score unavailable)"


def _value_with_unit(value: Any, unit: str, decimals: int) -> str:
    number = _number_text(value, decimals)
    return f"{number} {unit}" if number is not None else "Unavailable"


def _number_text(value: Any, decimals: int) -> str | None:
    return f"{float(value):.{decimals}f}" if _is_number(value) else None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _humanize(value: str) -> str:
    return value.replace("_", " ").strip().capitalize()


def _timezone(name: str | None) -> ZoneInfo | None:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _escape(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _bounded_display(value: Any, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip()[:maximum]


def _bounded_list(value: Any, maximum_items: int, maximum_chars: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value[:maximum_items] if (text := _bounded_display(item, maximum_chars))]
