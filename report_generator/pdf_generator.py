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


def render_pdf(context):
    """Render templates/reports/report.html. Returns (pdf_bytes, page_count)."""
    try:
        from weasyprint import HTML
        from weasyprint.text.fonts import FontConfiguration
    except (ImportError, OSError) as exc:
        # OSError: Pango/HarfBuzz system libraries are missing.
        raise PDFRenderError(f'WeasyPrint is not available: {exc}') from exc

    html = render_to_string('reports/report.html', {**context, 'fonts': font_urls()})
    document = HTML(string=html, url_fetcher=_make_fetcher()).render(font_config=FontConfiguration())
    pdf = document.write_pdf()
    return pdf, len(document.pages)


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
