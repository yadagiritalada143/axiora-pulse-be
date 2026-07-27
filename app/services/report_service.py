"""
Report Service — Backend Report Generator for Axiora Pulse Agents
──────────────────────────────────────────────────────────────────────────────
Generates backend downloadable reports (PDF and DOC/TXT format) per agent:
  - idea_validation_agent (Analysis 1: Problem Analysis)
  - market_research_agent (Analysis 2: Target Customer & Market Research)
  - full / all (Combined Multi-Agent Report)
"""
import io
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Try importing ReportLab for native PDF rendering
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.info("[ReportService] ReportLab not installed; using standard report renderer fallback.")


class ReportService:
    """Backend service that transforms agent results into PDF and Doc downloads."""

    def generate_report(
        self,
        agent_name: str,
        validation_result: Dict[str, Any],
        idea_info: Optional[Dict[str, Any]] = None,
        export_format: str = "pdf"
    ) -> Tuple[bytes, str, str]:
        """
        Main entry point to generate a report.
        Returns: (file_bytes, mime_type, filename)
        """
        agent_key = agent_name.lower().strip()
        fmt = export_format.lower().strip()
        if fmt not in ("pdf", "doc", "txt"):
            fmt = "pdf"

        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        idea_title = (idea_info or {}).get("idea_title") or "Startup_Idea"
        safe_title = "".join(c for c in idea_title if c.isalnum() or c in ("_", "-")).strip() or "Startup"

        if fmt == "doc" or fmt == "txt":
            return self._generate_doc_report(agent_key, validation_result, idea_info, safe_title, date_str)
        else:
            return self._generate_pdf_report(agent_key, validation_result, idea_info, safe_title, date_str)

    # ── DOC / TXT Generator ───────────────────────────────────────────────────

    def _generate_doc_report(
        self,
        agent_key: str,
        validation_result: Dict[str, Any],
        idea_info: Optional[Dict[str, Any]],
        safe_title: str,
        date_str: str
    ) -> Tuple[bytes, str, str]:
        """Generates a structured text/doc format report."""
        lines = []
        divider = "=" * 70
        subdivider = "-" * 40

        title_label = {
            "idea_validation_agent": "ANALYSIS 1: IDEA VALIDATION REPORT",
            "market_research_agent": "ANALYSIS 2: TARGET CUSTOMER & MARKET RESEARCH REPORT",
            "full": "COMPREHENSIVE MULTI-AGENT VALIDATION REPORT",
            "all": "COMPREHENSIVE MULTI-AGENT VALIDATION REPORT",
        }.get(agent_key, "AGENT ANALYSIS REPORT")

        lines.append(divider)
        lines.append(f"AXIORA PULSE — {title_label}")
        lines.append(f"Generated: {datetime.utcnow().strftime('%d %b %Y, %H:%M UTC')}")
        if idea_info and idea_info.get("idea_title"):
            lines.append(f"Venture: {idea_info.get('idea_title')}")
        lines.append(divider)
        lines.append("")

        agent_results = validation_result.get("agent_results", {})

        # ── Idea Validation Section ──────────────────────────────────────────
        if agent_key in ("idea_validation_agent", "full", "all"):
            iv = agent_results.get("idea_validation_agent", {}).get("data", {})
            score = validation_result.get("validation_score", iv.get("problem_clarity_score", "N/A"))
            verdict = str(validation_result.get("verdict", "N/A")).replace("_", " ").upper()

            lines.append("SECTION 1: PROBLEM ANALYSIS & IDEA VALIDATION")
            lines.append(subdivider)
            lines.append(f"Validation Score      : {score}/100")
            lines.append(f"Verdict               : {verdict}")
            lines.append(f"Confidence Rating     : {MathRoundPercent(validation_result.get('confidence_rating', iv.get('confidence', 0.5)))}%")
            if iv.get("pain_type"):
                lines.append(f"Pain Type             : {iv.get('pain_type')}")
            lines.append("")

            if iv.get("problem_statement_summary"):
                lines.append("Problem Statement Summary:")
                lines.append(f"  {iv.get('problem_statement_summary')}")
                lines.append("")

            if iv.get("falsifiable_problem_sentence"):
                lines.append("Falsifiable Problem Statement:")
                lines.append(f"  \"{iv.get('falsifiable_problem_sentence')}\"")
                lines.append("")

            strengths = validation_result.get("strengths", [])
            if strengths:
                lines.append("Strengths Identified:")
                for s in strengths:
                    lines.append(f"  ✓ {s}")
                lines.append("")

            risks = validation_result.get("risks", [])
            if risks:
                lines.append("Risks & Concerns:")
                for r in risks:
                    lines.append(f"  ⚠ {r}")
                lines.append("")

            red_flags = iv.get("red_flags", [])
            if red_flags:
                lines.append("Red Flags:")
                for rf in red_flags:
                    lines.append(f"  🚩 {rf}")
                lines.append("")

            assumptions = iv.get("assumption_list") or validation_result.get("assumptions", [])
            if assumptions:
                lines.append("Key Falsifiable Assumptions:")
                for a in assumptions:
                    lines.append(f"  • {a}")
                lines.append("")

            recs = validation_result.get("recommendations", [])
            if recs:
                lines.append("Recommended Next Steps:")
                for rec in recs:
                    lines.append(f"  → {rec}")
                lines.append("")

        # ── Market Research Section ──────────────────────────────────────────
        if agent_key in ("market_research_agent", "full", "all"):
            mr = agent_results.get("market_research_agent", {}).get("data", {})

            lines.append("SECTION 2: TARGET CUSTOMER & MARKET RESEARCH")
            lines.append(subdivider)
            lines.append(f"Market Opportunity Score : {mr.get('market_opportunity_score', 'N/A')}/100")
            lines.append(f"Audience Narrowness Score: {mr.get('audience_narrowness_score', 'N/A')}/100")
            lines.append(f"Analysis Confidence      : {MathRoundPercent(mr.get('confidence', 0.5))}%")
            lines.append("")

            if mr.get("market_opportunity_summary"):
                lines.append("Market Opportunity Summary:")
                lines.append(f"  {mr.get('market_opportunity_summary')}")
                lines.append("")

            if mr.get("primary_icp_summary"):
                lines.append("Primary Ideal Customer Profile (ICP):")
                lines.append(f"  {mr.get('primary_icp_summary')}")
                lines.append("")

            if mr.get("persona_summary"):
                lines.append("Buyer Persona Narrative:")
                lines.append(f"  {mr.get('persona_summary')}")
                lines.append("")

            segments = mr.get("target_customer_segments", [])
            if segments:
                lines.append("Target Customer Segments:")
                for seg in segments:
                    lines.append(f"  ◆ {seg}")
                lines.append("")

            sec_segments = mr.get("secondary_segments", [])
            if sec_segments:
                lines.append("Secondary Segments:")
                for sseg in sec_segments:
                    lines.append(f"  ◇ {sseg}")
                lines.append("")

            competitors = mr.get("competitor_overview", [])
            if competitors:
                lines.append("Competitor Overview & Substitutes:")
                for comp in competitors:
                    lines.append(f"  ⚡ {comp}")
                lines.append("")

            opp_signals = mr.get("opportunity_signals", [])
            if opp_signals:
                lines.append("Opportunity Signals:")
                for os in opp_signals:
                    lines.append(f"  ✅ {os}")
                lines.append("")

            risk_signals = mr.get("risk_signals", [])
            if risk_signals:
                lines.append("Market Risk Signals:")
                for rs in risk_signals:
                    lines.append(f"  ⚠ {rs}")
                lines.append("")

            mr_flags = mr.get("red_flags", [])
            if mr_flags:
                lines.append("Audience Red Flags:")
                for flag in mr_flags:
                    lines.append(f"  🚩 {flag}")
                lines.append("")

        lines.append(divider)
        lines.append("Axiora Pulse AI Orchestration Engine — Confidential Report")
        lines.append(divider)

        text_content = "\n".join(lines)
        file_bytes = text_content.encode("utf-8")
        filename = f"{safe_title}_{agent_key}_report_{date_str}.txt"
        return file_bytes, "text/plain; charset=utf-8", filename

    # ── PDF Generator ────────────────────────────────────────────────────────

    def _generate_pdf_report(
        self,
        agent_key: str,
        validation_result: Dict[str, Any],
        idea_info: Optional[Dict[str, Any]],
        safe_title: str,
        date_str: str
    ) -> Tuple[bytes, str, str]:
        """Generates a PDF format report using ReportLab if available, or structured text PDF fallback."""
        filename = f"{safe_title}_{agent_key}_report_{date_str}.pdf"

        if REPORTLAB_AVAILABLE:
            pdf_bytes = self._build_reportlab_pdf(agent_key, validation_result, idea_info)
            return pdf_bytes, "application/pdf", filename
        else:
            # Clean pure-python text fallback returned with text MIME type for universal compatibility
            txt_bytes, _, _ = self._generate_doc_report(agent_key, validation_result, idea_info, safe_title, date_str)
            return txt_bytes, "text/plain; charset=utf-8", filename.replace(".pdf", ".txt")

    # ── ReportLab PDF Builder ────────────────────────────────────────────────

    def _build_reportlab_pdf(
        self,
        agent_key: str,
        validation_result: Dict[str, Any],
        idea_info: Optional[Dict[str, Any]]
    ) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()

        # Custom Palette
        primary_color = colors.HexColor("#FF4F00")  # Axiora Orange
        dark_color = colors.HexColor("#0F172A")
        body_color = colors.HexColor("#334155")
        light_bg = colors.HexColor("#F8FAFC")
        purple_color = colors.HexColor("#8B5CF6")

        title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=16,
            textColor=primary_color,
            spaceAfter=4
        )
        subtitle_style = ParagraphStyle(
            'ReportSubtitle',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            textColor=colors.HexColor("#64748B"),
            spaceAfter=12
        )
        h2_style = ParagraphStyle(
            'SectionH2',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=12,
            textColor=dark_color,
            spaceBefore=10,
            spaceAfter=6
        )
        body_style = ParagraphStyle(
            'ReportBody',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9.5,
            textColor=body_color,
            leading=13,
            spaceAfter=6
        )
        list_style = ParagraphStyle(
            'ReportList',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            textColor=body_color,
            leading=12,
            leftIndent=12,
            spaceAfter=3
        )

        elements = []

        # Header Title
        report_name = {
            "idea_validation_agent": "Analysis 1 · Idea Validation Report",
            "market_research_agent": "Analysis 2 · Target Customer & Market Research Report",
            "full": "Full Multi-Agent Validation Report",
            "all": "Full Multi-Agent Validation Report",
        }.get(agent_key, "Agent Analysis Report")

        venture = (idea_info or {}).get("idea_title") or "Startup Venture"
        elements.append(Paragraph(f"<b>{report_name}</b>", title_style))
        elements.append(Paragraph(f"Venture: <b>{venture}</b> | Generated by Axiora Pulse Engine", subtitle_style))
        elements.append(HRFlowable(width="100%", thickness=1, color=primary_color, spaceAfter=10))

        agent_results = validation_result.get("agent_results", {})

        # ── Idea Validation Content ──────────────────────────────────────────
        if agent_key in ("idea_validation_agent", "full", "all"):
            iv = agent_results.get("idea_validation_agent", {}).get("data", {})
            score = validation_result.get("validation_score", iv.get("problem_clarity_score", "N/A"))
            verdict = str(validation_result.get("verdict", "N/A")).replace("_", " ").upper()

            elements.append(Paragraph("<b>1. Problem Analysis & Idea Validation</b>", h2_style))

            summary_table_data = [
                [
                    Paragraph(f"<b>Validation Score:</b> {score}/100", body_style),
                    Paragraph(f"<b>Verdict:</b> {verdict}", body_style),
                    Paragraph(f"<b>Confidence:</b> {MathRoundPercent(validation_result.get('confidence_rating', iv.get('confidence', 0.5)))}%", body_style)
                ]
            ]
            t = Table(summary_table_data, colWidths=[180, 180, 180])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), light_bg),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 8))

            if iv.get("problem_statement_summary"):
                elements.append(Paragraph("<b>Problem Summary:</b>", body_style))
                elements.append(Paragraph(iv.get("problem_statement_summary"), body_style))

            if iv.get("falsifiable_problem_sentence"):
                elements.append(Paragraph(f"<i>Falsifiable Problem Statement: \"{iv.get('falsifiable_problem_sentence')}\"</i>", body_style))

            strengths = validation_result.get("strengths", [])
            if strengths:
                elements.append(Paragraph("<b>Strengths:</b>", body_style))
                for s in strengths:
                    elements.append(Paragraph(f"• {s}", list_style))

            risks = validation_result.get("risks", [])
            if risks:
                elements.append(Paragraph("<b>Risks & Concerns:</b>", body_style))
                for r in risks:
                    elements.append(Paragraph(f"• {r}", list_style))

            red_flags = iv.get("red_flags", [])
            if red_flags:
                elements.append(Paragraph("<b>Red Flags:</b>", body_style))
                for rf in red_flags:
                    elements.append(Paragraph(f"• {rf}", list_style))

            elements.append(Spacer(1, 10))

        # ── Market Research Content ──────────────────────────────────────────
        if agent_key in ("market_research_agent", "full", "all"):
            mr = agent_results.get("market_research_agent", {}).get("data", {})
            m_score = mr.get("market_opportunity_score", "N/A")
            n_score = mr.get("audience_narrowness_score", "N/A")

            elements.append(Paragraph("<b>2. Target Customer & Market Research</b>", h2_style))

            mr_table_data = [
                [
                    Paragraph(f"<b>Market Score:</b> {m_score}/100", body_style),
                    Paragraph(f"<b>Audience Narrowness:</b> {n_score}/100", body_style),
                    Paragraph(f"<b>Confidence:</b> {MathRoundPercent(mr.get('confidence', 0.5))}%", body_style)
                ]
            ]
            t2 = Table(mr_table_data, colWidths=[180, 180, 180])
            t2.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), light_bg),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(t2)
            elements.append(Spacer(1, 8))

            if mr.get("market_opportunity_summary"):
                elements.append(Paragraph("<b>Market Opportunity Summary:</b>", body_style))
                elements.append(Paragraph(mr.get("market_opportunity_summary"), body_style))

            if mr.get("primary_icp_summary"):
                elements.append(Paragraph("<b>Primary Ideal Customer Profile (ICP):</b>", body_style))
                elements.append(Paragraph(mr.get("primary_icp_summary"), body_style))

            if mr.get("persona_summary"):
                elements.append(Paragraph(f"<i>Buyer Persona: {mr.get('persona_summary')}</i>", body_style))

            segments = mr.get("target_customer_segments", [])
            if segments:
                elements.append(Paragraph("<b>Target Customer Segments:</b>", body_style))
                for seg in segments:
                    elements.append(Paragraph(f"• {seg}", list_style))

            competitors = mr.get("competitor_overview", [])
            if competitors:
                elements.append(Paragraph("<b>Competitor Overview:</b>", body_style))
                for comp in competitors:
                    elements.append(Paragraph(f"• {comp}", list_style))

            opp_signals = mr.get("opportunity_signals", [])
            if opp_signals:
                elements.append(Paragraph("<b>Opportunity Signals:</b>", body_style))
                for os in opp_signals:
                    elements.append(Paragraph(f"• {os}", list_style))

            risk_signals = mr.get("risk_signals", [])
            if risk_signals:
                elements.append(Paragraph("<b>Market Risks:</b>", body_style))
                for rs in risk_signals:
                    elements.append(Paragraph(f"• {rs}", list_style))

            mr_flags = mr.get("red_flags", [])
            if mr_flags:
                elements.append(Paragraph("<b>Audience Red Flags:</b>", body_style))
                for flag in mr_flags:
                    elements.append(Paragraph(f"• {flag}", list_style))

        elements.append(Spacer(1, 14))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1"), spaceAfter=6))
        elements.append(Paragraph("<font size=7 color='#94A3B8'>Axiora Pulse AI Engine · Confidential Startup Intelligence Report</font>", body_style))

        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()


def MathRoundPercent(val: Any) -> int:
    """Helper to convert float confidence (0.0-1.0) into integer percentage."""
    try:
        f = float(val)
        return round(f * 100) if f <= 1.0 else round(f)
    except (ValueError, TypeError):
        return 50


# Global singleton
report_service = ReportService()
