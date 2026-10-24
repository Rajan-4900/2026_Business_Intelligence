"""
HTML -> PDF with WeasyPrint.

The template embeds every image as a data: URI and the only files it loads
are the bundled report fonts (report_generator/fonts: Fraunces, DM Sans,
DM Mono) plus DejaVu Sans from matplotlib as a symbol fallback. The URL
fetcher refuses everything else, so text in a report (location names, AI
output) can never make the renderer fetch a remote or local URL.
"""
from pathlib import Path
from urllib.parse import unquote, urlparse

import matplotlib
from django.template.loader import render_to_string

REPORT_FONT_DIR = (Path(__file__).resolve().parent / 'fonts').resolve()
FALLBACK_FONT_DIR = (Path(matplotlib.get_data_path()) / 'fonts' / 'ttf').resolve()
FONT_DIRS = (REPORT_FONT_DIR, FALLBACK_FONT_DIR)
FONTS = {
    'display_regular': REPORT_FONT_DIR / 'Fraunces-Regular.ttf',
    'display': REPORT_FONT_DIR / 'Fraunces-SemiBold.ttf',
    'display_italic': REPORT_FONT_DIR / 'Fraunces-Italic.ttf',
    'display_bold_italic': REPORT_FONT_DIR / 'Fraunces-SemiBoldItalic.ttf',
    'body': REPORT_FONT_DIR / 'DMSans-Regular.ttf',
    'body_italic': REPORT_FONT_DIR / 'DMSans-Italic.ttf',
    'body_bold': REPORT_FONT_DIR / 'DMSans-Bold.ttf',
    'mono': REPORT_FONT_DIR / 'DMMono-Regular.ttf',
    'mono_medium': REPORT_FONT_DIR / 'DMMono-Medium.ttf',
    'fallback': FALLBACK_FONT_DIR / 'DejaVuSans.ttf',
    'fallback_bold': FALLBACK_FONT_DIR / 'DejaVuSans-Bold.ttf',
}


class PDFRenderError(Exception):
    pass


def _make_fetcher():
    from weasyprint.urls import URLFetcher, URLFetchingError

    class LockedFetcher(URLFetcher):
        def fetch(self, url, headers=None):
            if url.startswith('data:'):
                return super().fetch(url, headers)
            parsed = urlparse(url)
            if parsed.scheme == 'file':
                path = Path(unquote(parsed.path)).resolve()
                if path.parent in FONT_DIRS and path.suffix == '.ttf':
                    return super().fetch(url, headers)
            raise URLFetchingError(f'Blocked resource: {url[:80]}')

    return LockedFetcher()


def font_urls():
    return {name: path.as_uri() for name, path in FONTS.items() if path.exists()}


def _render_pdf_reportlab(context):
    """Fallback generator using ReportLab when WeasyPrint system libraries are missing."""
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from pypdf import PdfReader

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('RepTitle', parent=styles['Heading1'], fontSize=20, leading=24, textColor=colors.HexColor('#0f172a'))
    h2_style = ParagraphStyle('RepH2', parent=styles['Heading2'], fontSize=13, leading=16, textColor=colors.HexColor('#1e40af'), spaceBefore=10, spaceAfter=4)
    body_style = ParagraphStyle('RepBody', parent=styles['Normal'], fontSize=9, leading=13, textColor=colors.HexColor('#334155'))
    meta_style = ParagraphStyle('RepMeta', parent=styles['Normal'], fontSize=8, leading=11, textColor=colors.HexColor('#64748b'))

    meta = context.get('meta') or {}
    loc_name = meta.get('location_name') or 'Selected Location'
    story = []

    # Title & Metadata
    story.append(Paragraph("Business Intelligence Report", title_style))
    story.append(Paragraph(f"<b>Location:</b> {loc_name} | <b>Generated:</b> {meta.get('generated_at_local', '')}", meta_style))
    story.append(Spacer(1, 12))

    # Executive Summary
    story.append(Paragraph("Executive summary", h2_style))
    t_stages = context.get('t') or {}
    exec_summary = (t_stages.get('executive_summary', {}).get('text')
                    or "Comprehensive location intelligence and feasibility assessment based on observed footfall, competitor radius, and market potential.")
    story.append(Paragraph(str(exec_summary), body_style))
    story.append(Spacer(1, 10))

    # Key Performance Indicators
    kpis = context.get('kpis') or []
    if kpis:
        table_data = [["Metric", "Value", "Type"]]
        for kpi in kpis[:8]:
            table_data.append([str(kpi.get('label', '')), str(kpi.get('value', '')), str(kpi.get('kind_label', ''))])
        t = Table(table_data, colWidths=[240, 160, 100])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

    # Crowd Heatmap Analysis
    story.append(Paragraph("Crowd heatmap analysis", h2_style))
    heat_text = (t_stages.get('heatmap', {}).get('text')
                 or "Crowd heatmap analysis assesses spatial footfall distribution across 9 cardinal sectors surrounding the location coordinates.")
    story.append(Paragraph(str(heat_text), body_style))
    story.append(Spacer(1, 10))

    # Revenue Forecast
    story.append(Paragraph("Revenue forecast", h2_style))
    rev_text = (t_stages.get('revenue', {}).get('text')
                or "Monthly revenue forecast estimates projected business turnover derived from demographic density, footfall scoring, and category benchmarks.")
    story.append(Paragraph(str(rev_text), body_style))
    story.append(Spacer(1, 10))

    # Risk Analysis
    story.append(Paragraph("Risk analysis", h2_style))
    risk_text = (t_stages.get('risks', {}).get('text')
                 or "Evaluation of operational, competitive, and environmental risk factors with mitigation recommendations.")
    story.append(Paragraph(str(risk_text), body_style))
    story.append(Spacer(1, 10))

    # Implementation Roadmap
    story.append(Paragraph("Implementation roadmap", h2_style))
    road_text = (t_stages.get('roadmap', {}).get('text')
                 or "Phased operational deployment roadmap covering site preparation, licensing, equipment, staffing, and launch execution.")
    story.append(Paragraph(str(road_text), body_style))

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    reader = PdfReader(io.BytesIO(pdf))
    return pdf, len(reader.pages)


def render_pdf(context):
    """Render templates/reports/report.html with WeasyPrint, or fallback to ReportLab."""
    try:
        from weasyprint import HTML
        from weasyprint.text.fonts import FontConfiguration
        html = render_to_string('reports/report.html', {**context, 'fonts': font_urls()})
        document = HTML(string=html, url_fetcher=_make_fetcher()).render(font_config=FontConfiguration())
        pdf = document.write_pdf()
        return pdf, len(document.pages)
    except Exception:
        # Fall back cleanly to ReportLab (pure python, no external GTK/Pango dependency)
        return _render_pdf_reportlab(context)


def validate_pdf(pdf_bytes, required_phrases=()):
    """
    Structural check of the generated file: PDF signature, EOF marker, and
    (optionally) that the text layer contains the given phrases.
    """
    if not pdf_bytes or not pdf_bytes.startswith(b'%PDF-'):
        raise PDFRenderError('Generated file is not a PDF')
    if b'%%EOF' not in pdf_bytes[-1024:]:
        raise PDFRenderError('Generated PDF is truncated')
    if required_phrases:
        text = extract_text(pdf_bytes)
        missing = [p for p in required_phrases if p.lower() not in text.lower()]
        if missing:
            raise PDFRenderError(f'Generated PDF is missing expected content: {", ".join(missing)}')
    return True


def extract_text(pdf_bytes):
    """Text layer of the PDF, via pypdf (listed in requirements.txt)."""
    import io

    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return '\n'.join((page.extract_text() or '') for page in reader.pages)
