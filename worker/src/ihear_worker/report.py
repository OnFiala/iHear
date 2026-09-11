from __future__ import annotations

from collections import Counter
from datetime import datetime
from io import BytesIO
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from .astra import APPROVED_TIPS


INK = colors.HexColor("#19323C")
MINT = colors.HexColor("#74C9B8")
PALE = colors.HexColor("#EAF7F4")
CORAL = colors.HexColor("#E87965")
MUTED = colors.HexColor("#66777E")


class BarChart(Flowable):
    def __init__(self, values: list[tuple[str, float]], width: float = 160 * mm, height: float = 48 * mm):
        super().__init__()
        self.values = values
        self.width = width
        self.height = height

    def draw(self) -> None:
        if not self.values:
            return
        canvas = self.canv
        left = 30 * mm
        value_label_width = 24 * mm
        usable = self.width - left - value_label_width
        bar_height = min(7 * mm, (self.height - 4 * mm) / len(self.values))
        canvas.setFont("Helvetica", 8)
        for index, (label, value) in enumerate(self.values):
            y = self.height - (index + 1) * bar_height
            canvas.setFillColor(MUTED)
            canvas.drawRightString(left - 2 * mm, y + 1.5 * mm, label[:28])
            canvas.setFillColor(PALE)
            canvas.roundRect(left, y, usable, bar_height - 2 * mm, 2 * mm, fill=1, stroke=0)
            canvas.setFillColor(MINT)
            normalized = min(1.0, max(0.0, (value + 100.0) / 100.0))
            canvas.roundRect(left, y, usable * normalized, bar_height - 2 * mm, 2 * mm, fill=1, stroke=0)
            canvas.setFillColor(INK)
            canvas.drawRightString(self.width, y + 1.5 * mm, f"{value:.1f} dBFS")


def _footer(canvas: Any, document: Any) -> None:
    canvas.saveState()
    canvas.setStrokeColor(PALE)
    canvas.line(20 * mm, 16 * mm, A4[0] - 20 * mm, 16 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(20 * mm, 10 * mm, "iHear listening report - measurements and model estimates")
    canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Page {document.page}")
    canvas.restoreState()


def generate_report(patient: dict[str, Any], events: list[dict[str, Any]], input_revision: int) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,
        title=f"iHear report - {patient.get('display_name', 'Patient')}",
        author="iHear",
        subject=f"Listening evidence revision {input_revision}",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24, textColor=INK, leading=29, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, textColor=INK, spaceBefore=9 * mm, spaceAfter=3 * mm))
    styles.add(ParagraphStyle(name="BodyMuted", parent=styles["BodyText"], fontSize=9, leading=13, textColor=MUTED))
    styles["BodyText"].fontSize = 9
    styles["BodyText"].leading = 13

    ready = [event for event in events if isinstance(event.get("analysis"), dict)]
    counts = Counter(event.get("kind") for event in events)
    aid_summary = _aid_summary(patient.get("aids"))
    follow_up = _bounded_display(patient.get("follow_up_date"), 40) or "Not set"
    timezone_name = _bounded_display(patient.get("timezone"), 64)
    report_timezone = _timezone(timezone_name)
    timezone_label = timezone_name if report_timezone else "Not available"
    story: list[Any] = [
        Paragraph("iHear listening report", styles["ReportTitle"]),
        Paragraph(f"Patient: {_escape(patient.get('display_name') or 'Unknown')} &nbsp;&nbsp; Evidence revision: {input_revision}", styles["BodyMuted"]),
        Paragraph(f"Follow-up: {_escape(follow_up)} &nbsp;&nbsp; Hearing aids: {_escape(aid_summary)} &nbsp;&nbsp; Timezone: {_escape(timezone_label)}", styles["BodyMuted"]),
        Spacer(1, 6 * mm),
        Paragraph("Purpose and limits", styles["Section"]),
        Paragraph(
            "Illustrative demo only. Use synthetic profiles. "
            "This report organizes patient feedback, deterministic signal measurements, and model estimates. "
            "It is not a diagnosis, does not measure calibrated sound pressure or hearing thresholds, and does not prescribe hearing-aid settings. Clinical interpretation belongs to the clinician.",
            styles["BodyText"],
        ),
        Paragraph("Listening overview", styles["Section"]),
        Table(
            [["Recorded events", str(len(events))], ["Understood", str(counts.get("understood", 0))], ["Difficult", str(counts.get("difficult", 0))], ["Analysed", str(len(ready))]],
            colWidths=[55 * mm, 30 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), PALE), ("TEXTCOLOR", (0, 0), (-1, -1), INK),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.5, colors.white),
                ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]),
        ),
    ]

    rms_values = []
    for index, event in enumerate(ready[-12:], 1):
        rms = event["analysis"].get("rms_dbfs")
        if isinstance(rms, (int, float)):
            rms_values.append((str(index), float(rms)))
    signal_story: list[Any] = [
        Paragraph("Relative signal level by analysed event", styles["Section"]),
    ]
    if rms_values:
        signal_story.extend([
            Paragraph("Bars use a fixed -100 to 0 dBFS axis; labels show the measured RMS dBFS. dBFS is an uncalibrated digital level and cannot be compared with dB HL or SPL.", styles["BodyMuted"]),
            Spacer(1, 3 * mm),
            BarChart(rms_values),
        ])
    else:
        signal_story.append(Paragraph(
            "No measured RMS dBFS values are available for this report.",
            styles["BodyMuted"],
        ))
    story.extend(signal_story + [
        KeepTogether([
            Paragraph("Method notes", styles["Section"]),
            Paragraph(
                "Frequency-band energy and spectral centroid come from native-rate STFT analysis. Speech activity is a Silero VAD estimate after resampling to 16 kHz. Acoustic labels are YAMNet estimates after resampling to 16 kHz. No transcription or speaker identification is performed.",
                styles["BodyText"],
            ),
        ]),
        PageBreak(),
        Paragraph("Event evidence", styles["ReportTitle"]),
    ])

    for event_index, event in enumerate(events, 1):
        analysis = event.get("analysis") or {}
        speech = analysis.get("speech_activity") or {}
        categories = analysis.get("acoustic_categories") or {}
        category_text = ", ".join(
            _category_display(item)
            for item in categories.get("categories", [])[:3]
            if isinstance(item, dict)
        ) or categories.get("status", "unavailable")
        interpretation = event.get("interpretation") or {}
        interpretation_status = str(event.get("interpretation_status") or "unavailable")
        rows = [
            ["Feedback", str(event.get("kind") or "unknown")],
            ["Captured", _local_timestamp(event.get("captured_at"), report_timezone)],
            ["Context", " / ".join(filter(None, [str(event.get("difficulty") or ""), str(event.get("environment") or "")])) or "Not supplied"],
            ["Duration", f"{analysis.get('duration_seconds', 'unavailable')} s"],
            ["RMS / peak", f"{_measured_value(analysis.get('rms_dbfs'))} / {_measured_value(analysis.get('peak_dbfs'))} dBFS"],
            ["Quality flags", ", ".join(analysis.get("quality_flags", [])) or "None"],
            ["Speech estimate", f"{speech.get('status', 'unavailable')}" + (f", fraction {speech.get('fraction'):.2f}" if isinstance(speech.get("fraction"), (int, float)) else "")],
            ["Acoustic estimates", category_text],
            ["AI interpretation", interpretation_status],
        ]
        if interpretation_status == "ready" and isinstance(interpretation, dict):
            summary = _bounded_display(interpretation.get("summary"), 600)
            observations = _bounded_list(interpretation.get("observations"), 4, 240)
            limitations = _bounded_list(interpretation.get("limitations"), 4, 240)
            tip_ids = interpretation.get("tip_ids") if isinstance(interpretation.get("tip_ids"), list) else []
            tips = [APPROVED_TIPS[tip_id] for tip_id in tip_ids[:3] if tip_id in APPROVED_TIPS]
            rows.extend([
                ["Summary", summary or "Unavailable"],
                ["Observations", " | ".join(observations) or "None"],
                ["Patient tips", " | ".join(tips) or "None"],
                ["Limitations", " | ".join(limitations) or "None"],
            ])
        table_rows = [
            [Paragraph(_escape(label), styles["BodyText"]), Paragraph(_escape(value), styles["BodyText"])]
            for label, value in rows
        ]
        story.append(KeepTogether([
            Paragraph(
                f"Moment {event_index} &nbsp; {_escape(str(event.get('id') or 'unknown')[:8])}",
                styles["Section"],
            ),
            Table(table_rows, colWidths=[38 * mm, 125 * mm], style=TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("TEXTCOLOR", (0, 0), (-1, -1), INK), ("BACKGROUND", (0, 0), (0, -1), PALE),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D8E8E4")),
                ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ])),
        ]))

    document.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return output.getvalue()


def _escape(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _bounded_display(value: Any, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip()[:maximum]


def _bounded_list(value: Any, maximum_items: int, maximum_chars: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        text for item in value[:maximum_items]
        if (text := _bounded_display(item, maximum_chars))
    ]


def _aid_summary(value: Any) -> str:
    if not isinstance(value, dict):
        return "Not supplied"
    side = _bounded_display(value.get("side"), 24)
    models = []
    for channel in ("left", "right"):
        device = value.get(channel)
        if isinstance(device, dict):
            model = _bounded_display(device.get("model"), 60)
            if model:
                models.append(f"{channel}: {model}")
    return "; ".join(filter(None, [side, *models])) or "Not supplied"


def _timezone(name: str | None) -> ZoneInfo | None:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _local_timestamp(value: Any, timezone: ZoneInfo | None) -> str:
    original = str(value or "unknown")
    if timezone is None or not isinstance(value, str):
        return original
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return original
    if parsed.tzinfo is None:
        return original
    return parsed.astimezone(timezone).strftime("%Y-%m-%d %H:%M %Z")


def _measured_value(value: Any) -> str:
    return str(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else "unavailable"


def _category_display(item: dict[str, Any]) -> str:
    label = _bounded_display(item.get("label"), 80) or "Unlabelled category"
    score = item.get("score")
    if isinstance(score, (int, float)) and not isinstance(score, bool):
        return f"{label} ({float(score):.2f})"
    return f"{label} (score unavailable)"
