"""
PDF Export Service — generates professional PDF reports using ReportLab.

Produces a multi-page, formatted PDF containing all report sections:
  - Cover page with metadata
  - Executive Summary
  - Competitor Overview
  - Latest News
  - Pricing Summary
  - SWOT Analysis
  - Strategic Recommendations
  - Sources & References
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── Colour palette ────────────────────────────────────────────────────────
DARK_BG    = (0.04, 0.06, 0.12)   # Deep navy
PRIMARY    = (0.38, 0.41, 0.97)   # Indigo
ACCENT     = (0.25, 0.75, 0.60)   # Emerald
WARNING    = (0.95, 0.60, 0.20)   # Amber
DANGER     = (0.85, 0.25, 0.25)   # Red
WHITE      = (1.0,  1.0,  1.0)
LIGHT_GRAY = (0.85, 0.87, 0.90)
MID_GRAY   = (0.55, 0.58, 0.65)
CARD_BG    = (0.06, 0.09, 0.18)   # Slightly lighter than DARK_BG


def _hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def generate_pdf(
    report_data: dict[str, Any],
    export_dir: str,
    report_id: str,
) -> str:
    """
    Generate a PDF for the given report data.

    Parameters
    ----------
    report_data : dict
        Fields from the Report ORM model.
    export_dir : str
        Directory to write the PDF file.
    report_id : str
        Used to name the file.

    Returns
    -------
    str
        Absolute path to the generated PDF file.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm, mm
        from reportlab.platypus import (
            HRFlowable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
        from reportlab.lib.colors import Color, HexColor

    except ImportError as exc:
        raise RuntimeError(f"ReportLab not installed: {exc}") from exc

    os.makedirs(export_dir, exist_ok=True)
    filename = f"report_{report_id}.pdf"
    filepath = os.path.join(export_dir, filename)

    # ── Page setup ────────────────────────────────────────────────────────
    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        leftMargin=2*cm,
        rightMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm,
        title=f"Competitive Intelligence Report — {report_data.get('competitor_name', 'Unknown')}",
        author="Competitive Intelligence Briefing Crew",
    )

    W, H = A4

    # ── Colour helpers ────────────────────────────────────────────────────
    c_primary   = Color(*PRIMARY)
    c_accent    = Color(*ACCENT)
    c_warning   = Color(*WARNING)
    c_danger    = Color(*DANGER)
    c_dark      = Color(*DARK_BG)
    c_card      = Color(*CARD_BG)
    c_white     = colors.white
    c_light     = Color(*LIGHT_GRAY)
    c_mid       = Color(*MID_GRAY)

    # ── Styles ────────────────────────────────────────────────────────────
    base = getSampleStyleSheet()

    def make_style(name, **kwargs):
        return ParagraphStyle(name, **kwargs)

    s_cover_title = make_style(
        "CoverTitle",
        fontName="Helvetica-Bold",
        fontSize=28,
        leading=34,
        textColor=c_white,
        alignment=TA_LEFT,
    )
    s_cover_sub = make_style(
        "CoverSub",
        fontName="Helvetica",
        fontSize=13,
        leading=18,
        textColor=c_light,
        alignment=TA_LEFT,
    )
    s_cover_meta = make_style(
        "CoverMeta",
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=c_mid,
        alignment=TA_LEFT,
    )
    s_section_title = make_style(
        "SectionTitle",
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=c_primary,
        spaceBefore=14,
        spaceAfter=4,
    )
    s_body = make_style(
        "Body",
        fontName="Helvetica",
        fontSize=10,
        leading=15,
        textColor=colors.black,
        spaceAfter=6,
    )
    s_bullet = make_style(
        "Bullet",
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.black,
        leftIndent=14,
        bulletIndent=0,
        spaceAfter=3,
    )
    s_news_title = make_style(
        "NewsTitle",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=13,
        textColor=colors.black,
    )
    s_news_meta = make_style(
        "NewsMeta",
        fontName="Helvetica",
        fontSize=8,
        leading=12,
        textColor=c_mid,
    )
    s_footer = make_style(
        "Footer",
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=c_mid,
        alignment=TA_CENTER,
    )
    s_rec = make_style(
        "Rec",
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.black,
        leftIndent=20,
        spaceAfter=5,
    )

    # ── Page background callback ──────────────────────────────────────────
    def _on_page(canvas, doc):
        canvas.saveState()
        # Light header bar
        canvas.setFillColor(c_primary)
        canvas.rect(0, H - 8*mm, W, 4*mm, fill=1, stroke=0)
        # Footer
        canvas.setFillColor(c_mid)
        canvas.setFont("Helvetica", 7)
        page_str = f"Page {doc.page}  |  Competitive Intelligence Briefing Crew"
        canvas.drawCentredString(W / 2, 12*mm, page_str)
        canvas.restoreState()

    # ── Build story ───────────────────────────────────────────────────────
    story = []

    competitor   = report_data.get("competitor_name", "Unknown")
    industry     = report_data.get("industry", "")
    region       = report_data.get("region", "")
    created_at   = report_data.get("created_at", datetime.now(timezone.utc))
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at)
        except Exception:
            created_at = datetime.now(timezone.utc)
    date_str = created_at.strftime("%B %d, %Y")

    exec_summary     = report_data.get("executive_summary") or ""
    comp_overview    = report_data.get("competitor_overview") or ""
    pricing_summary  = report_data.get("pricing_summary") or ""
    swot             = report_data.get("swot_analysis") or {}
    recommendations  = report_data.get("recommendations") or []
    latest_news      = report_data.get("latest_news") or []
    sources          = report_data.get("sources") or []

    def hr(color=c_primary, width=1, dash=None):
        return HRFlowable(
            width="100%",
            thickness=width,
            color=color,
            spaceAfter=6,
            spaceBefore=6,
            dash=dash,
        )

    # ─── COVER PAGE ───────────────────────────────────────────────────────
    # Top accent bar via table
    story.append(Spacer(1, 1.5*cm))
    story.append(Paragraph("COMPETITIVE INTELLIGENCE REPORT", s_cover_meta))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(competitor, s_cover_title))
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph(f"{industry}  ·  {region}", s_cover_sub))
    story.append(Spacer(1, 0.6*cm))
    story.append(hr(c_primary, 2))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(f"Report Generated: {date_str}", s_cover_meta))
    story.append(Paragraph("Prepared by: Competitive Intelligence Briefing Crew", s_cover_meta))
    story.append(Spacer(1, 2*cm))

    # ─── EXECUTIVE SUMMARY ────────────────────────────────────────────────
    story.append(Paragraph("Executive Summary", s_section_title))
    story.append(hr())
    if exec_summary:
        for para in exec_summary.split("\n\n"):
            if para.strip():
                story.append(Paragraph(para.strip(), s_body))
    else:
        story.append(Paragraph("Executive summary not available.", s_body))
    story.append(Spacer(1, 0.4*cm))

    # ─── COMPETITOR OVERVIEW ─────────────────────────────────────────────
    story.append(Paragraph("Competitor Overview", s_section_title))
    story.append(hr())
    if comp_overview:
        for para in comp_overview.split("\n\n"):
            if para.strip():
                story.append(Paragraph(para.strip(), s_body))
    else:
        story.append(Paragraph("Competitor overview not available.", s_body))
    story.append(Spacer(1, 0.4*cm))

    # ─── LATEST NEWS ─────────────────────────────────────────────────────
    story.append(Paragraph("Latest News & Market Activity", s_section_title))
    story.append(hr())
    if latest_news:
        for item in latest_news[:8]:
            title = item.get("title", "No title")
            source = item.get("source", "")
            pub = item.get("published_at", "")[:10]
            url = item.get("url", "")
            summary = item.get("summary", "")

            story.append(Paragraph(f"• {title}", s_news_title))
            meta = f"{source}"
            if pub:
                meta += f" · {pub}"
            story.append(Paragraph(meta, s_news_meta))
            if summary:
                story.append(Paragraph(summary[:200], s_body))
            story.append(Spacer(1, 0.2*cm))
    else:
        story.append(Paragraph("No recent news articles found.", s_body))
    story.append(Spacer(1, 0.4*cm))

    # ─── PRICING SUMMARY ─────────────────────────────────────────────────
    story.append(Paragraph("Pricing Analysis", s_section_title))
    story.append(hr())
    if pricing_summary:
        for para in pricing_summary.split("\n\n"):
            if para.strip():
                story.append(Paragraph(para.strip(), s_body))
    else:
        story.append(Paragraph("Pricing information not publicly available.", s_body))
    story.append(Spacer(1, 0.4*cm))

    # ─── SWOT ANALYSIS ───────────────────────────────────────────────────
    story.append(Paragraph("SWOT Analysis", s_section_title))
    story.append(hr())

    if swot:
        swot_data = [
            ["STRENGTHS ✓", "WEAKNESSES ✗"],
            [
                "\n".join(f"• {s}" for s in swot.get("strengths", ["N/A"])),
                "\n".join(f"• {w}" for w in swot.get("weaknesses", ["N/A"])),
            ],
            ["OPPORTUNITIES ↑", "THREATS ⚠"],
            [
                "\n".join(f"• {o}" for o in swot.get("opportunities", ["N/A"])),
                "\n".join(f"• {t}" for t in swot.get("threats", ["N/A"])),
            ],
        ]

        col_w = (doc.width / 2) - 0.2*cm
        swot_table = Table(
            [
                [Paragraph("STRENGTHS", make_style("S", fontName="Helvetica-Bold", fontSize=9, textColor=c_accent)),
                 Paragraph("WEAKNESSES", make_style("S", fontName="Helvetica-Bold", fontSize=9, textColor=c_danger))],
                [Paragraph(swot_data[1][0], s_body), Paragraph(swot_data[1][1], s_body)],
                [Paragraph("OPPORTUNITIES", make_style("S", fontName="Helvetica-Bold", fontSize=9, textColor=c_primary)),
                 Paragraph("THREATS", make_style("S", fontName="Helvetica-Bold", fontSize=9, textColor=c_warning))],
                [Paragraph(swot_data[3][0], s_body), Paragraph(swot_data[3][1], s_body)],
            ],
            colWidths=[col_w, col_w],
        )
        swot_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), Color(0.05, 0.35, 0.20)),
            ("BACKGROUND", (1, 0), (1, 0), Color(0.35, 0.05, 0.05)),
            ("BACKGROUND", (0, 2), (0, 2), Color(0.05, 0.10, 0.35)),
            ("BACKGROUND", (1, 2), (1, 2), Color(0.35, 0.25, 0.02)),
            ("BACKGROUND", (0, 1), (0, 1), colors.Color(0.93, 0.97, 0.93)),
            ("BACKGROUND", (1, 1), (1, 1), colors.Color(0.97, 0.93, 0.93)),
            ("BACKGROUND", (0, 3), (0, 3), colors.Color(0.92, 0.94, 0.98)),
            ("BACKGROUND", (1, 3), (1, 3), colors.Color(0.99, 0.96, 0.90)),
            ("TOPPADDING",  (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, c_light),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(swot_table)
    else:
        story.append(Paragraph("SWOT analysis not available.", s_body))
    story.append(Spacer(1, 0.4*cm))

    # ─── RECOMMENDATIONS ─────────────────────────────────────────────────
    story.append(Paragraph("Strategic Recommendations", s_section_title))
    story.append(hr())
    if recommendations:
        for i, rec in enumerate(recommendations, 1):
            story.append(Paragraph(f"{i}.  {rec}", s_rec))
    else:
        story.append(Paragraph("No recommendations generated.", s_body))
    story.append(Spacer(1, 0.4*cm))

    # ─── SOURCES ─────────────────────────────────────────────────────────
    story.append(Paragraph("Sources & References", s_section_title))
    story.append(hr())
    if sources:
        for src in sources[:10]:
            title_text = src.get("title", src.get("url", "Unknown"))
            url_text   = src.get("url", "")
            src_type   = src.get("source", "Web")
            story.append(
                Paragraph(
                    f"• <b>{title_text}</b> [{src_type}]<br/>"
                    f"<font size='8' color='grey'>{url_text}</font>",
                    s_body,
                )
            )
    else:
        story.append(Paragraph("No sources available.", s_body))

    story.append(Spacer(1, 1*cm))
    story.append(hr(c_mid, 0.5))
    story.append(
        Paragraph(
            f"Competitive Intelligence Briefing Crew  ·  {date_str}  ·  Confidential",
            s_footer,
        )
    )

    # ── Build PDF ─────────────────────────────────────────────────────────
    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    logger.info("PDF generated: %s", filepath)
    return filepath
