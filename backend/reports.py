"""Portable Markdown and Unicode PDF exports for completed research runs."""

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from i18n import tr


def markdown_report(run):
    result = run.get("result") or {}
    stats = result.get("research_stats") or {}
    reflection = run.get("reflection") or {}
    lines = [
        f"# {run.get('query', 'INET research')}",
        "",
        result.get("answer") or tr("Ответ не сформирован.", "No answer was produced."),
        "",
        tr("## Метрики", "## Metrics"),
        "",
    ]
    for label, key in [
        (tr("Найдено источников", "Sources found"), "discovered_sources"),
        (tr("Прочитано сайтов", "Sites read"), "sites_read"),
        (tr("Непрочитано сайтов", "Sites not read"), "sites_unread"),
        (tr("Домены", "Domains"), "domains_read"),
        (tr("Сообщения агента", "Agent messages"), "agent_messages_used"),
        (tr("Инструментальные вызовы", "Tool calls"), "tool_calls_used"),
    ]:
        if key in stats:
            lines.append(f"- {label}: {stats[key]}")
    lines += ["", tr("## Источники", "## Sources"), ""]
    for index, source in enumerate(result.get("sources", []), 1):
        lines.append(f"{index}. [{source.get('title') or source.get('url')}]({source.get('url')})")
    if reflection:
        summary = reflection.get("summary") or {}
        lines += [
            "",
            tr("## Рефлексия", "## Reflection"),
            "",
            tr(
                f"Статус: {reflection.get('status', '—')}; уровень: {reflection.get('level', '—')}/4.",
                f"Status: {reflection.get('status', '—')}; level: {reflection.get('level', '—')}/4.",
            ),
        ]
        if summary:
            lines.append(
                tr(
                    f"Восстановлено источников: {summary.get('recovered', 0)}; альтернативных маршрутов: {summary.get('alternatives', 0)}; неудачных экспериментов: {summary.get('failed_experiments', 0)}.",
                    f"Recovered sources: {summary.get('recovered', 0)}; alternative routes: {summary.get('alternatives', 0)}; failed experiments: {summary.get('failed_experiments', 0)}.",
                )
            )
    return "\n".join(lines).strip() + "\n"


def pdf_report(run):
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak

    font_path = next(
        (
            path
            for path in (
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "C:/Windows/Fonts/arial.ttf",
            )
            if Path(path).exists()
        ),
        None,
    )
    font = "Helvetica"
    if font_path:
        font = "INETUnicode"
        pdfmetrics.registerFont(TTFont(font, font_path))
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "InetTitle",
        parent=styles["Title"],
        fontName=font,
        fontSize=20,
        leading=25,
        textColor="#24463d",
    )
    body = ParagraphStyle(
        "InetBody",
        parent=styles["BodyText"],
        fontName=font,
        fontSize=9,
        leading=14,
        alignment=TA_LEFT,
    )
    heading = ParagraphStyle("InetHeading", parent=body, fontSize=13, leading=18, spaceBefore=8, spaceAfter=5)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=run.get("query", "INET research"),
    )
    result = run.get("result") or {}
    story = [
        Paragraph(escape(run.get("query", "INET research")), title),
        Spacer(1, 6 * mm),
    ]
    for block in (result.get("answer") or tr("Ответ не сформирован.", "No answer was produced.")).split(
        "\n\n"
    ):
        story.append(Paragraph(escape(block).replace("\n", "<br/>"), body))
        story.append(Spacer(1, 2 * mm))
    story += [PageBreak(), Paragraph(tr("Источники", "Sources"), heading)]
    for index, source in enumerate(result.get("sources", []), 1):
        story.append(
            Paragraph(
                f"{index}. {escape(source.get('title') or source.get('url', ''))}<br/><font color='#39796b'>{escape(source.get('url', ''))}</font>",
                body,
            )
        )
    doc.build(story)
    return buffer.getvalue()
