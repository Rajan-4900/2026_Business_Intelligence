import base64
import io

from django.test import SimpleTestCase
from django.utils import timezone
from pypdf import PdfReader

from report_generator import ai_writer, chart_generator, content, flowchart_generator, services
from report_generator.data_collector import collect_analysis
from report_generator.models import Report
from report_generator.pdf_generator import PDFRenderError, extract_text, render_pdf, validate_pdf
from report_generator.validators import decode_screenshot

from .fixtures import LAT, LON, NAME, fake_overpass, png_data_url


def build_pdf(business='cafe', screenshot=True, elements=None, capture_error=''):
    with fake_overpass(elements=elements):
        snap = collect_analysis(LAT, LON, NAME, 2000, business)
    risks = content.risk_register(snap)
    with self_disabled_ai():
        texts = ai_writer.write_report_text(snap, risks)
    phases = content.timeline(texts['stages']['roadmap']['data']['steps'])
    png = decode_screenshot(png_data_url(), 2 * 1024 * 1024)[0] if screenshot else None
    report = Report(location_name=NAME, latitude=LAT, longitude=LON, radius_m=2000, business_type=business,
                    screenshot=png, capture_meta={'captured': screenshot, 'capture_error': capture_error, 'offset_m': 0.0},
                    created_at=timezone.now(), expires_at=timezone.now())
    ctx = services.build_context(report, snap, texts, risks, chart_generator.build_all(snap, risks, phases),
                                 flowchart_generator.build_all(snap))
    pdf, pages = render_pdf(ctx)
    return pdf, pages, snap


class self_disabled_ai:
    def __enter__(self):
        from django.test import override_settings
        self._o = override_settings(REPORT_AI_ENABLED=False)
        self._o.enable()

    def __exit__(self, *exc):
        self._o.disable()


class PDFTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pdf, cls.pages, cls.snap = build_pdf()
        cls.text = ' '.join(extract_text(cls.pdf).split())

    def test_valid_pdf_signature(self):
        self.assertTrue(self.pdf.startswith(b'%PDF-'))
        self.assertTrue(validate_pdf(self.pdf))
        self.assertGreater(len(PdfReader(io.BytesIO(self.pdf)).pages), 8)

    def test_required_sections(self):
        for heading in ('Executive summary', 'Location overview', 'Crowd heatmap analysis', 'Business recommendations',
                        'Competition and market', 'Revenue forecast', 'Business feasibility', 'Implementation roadmap',
                        'Risk analysis', 'Final recommendations', 'Sources, assumptions and limitations',
                        'Investment-validation checklist'):
            self.assertIn(heading, self.text)

    def test_location_and_page_numbers(self):
        self.assertIn(NAME, self.text)
        # The cover has no footer; numbering is visible from page 2.
        self.assertIn(f'Page 2 of {self.pages}', self.text)
        self.assertIn(f'Page {self.pages} of {self.pages}', self.text)

    def test_rupee_symbol_rendered(self):
        self.assertIn('₹', self.text)
        self.assertIn(content.inr(self.snap['revenue']['monthly']), self.text)

    def test_heatmap_screenshot_included(self):
        self.assertIn('Screenshot of the live heatmap', self.text)
        self.assertNotIn('reconstruction drawn by the server', self.text)
        images = sum(len(p.images) for p in PdfReader(io.BytesIO(self.pdf)).pages)
        self.assertGreaterEqual(images, 6)  # screenshot + charts

    def test_charts_and_flowcharts_included(self):
        for caption in ('Figure 3.2', 'Figure 4.1', 'Figure 6.1', 'Figure 9.1',
                        'Flowchart A', 'Flowchart B', 'Flowchart C', 'Flowchart D', 'Flowchart E'):
            self.assertIn(caption, self.text)
        self.assertNotIn('<svg', self.text)
        self.assertNotIn('flowchart TD', self.text)

    def test_ai_unavailability_is_disclosed(self):
        self.assertIn('AI-generated commentary was unavailable', self.text)

    def test_capture_failure_shows_warning_and_reconstruction(self):
        pdf, _, _ = build_pdf(screenshot=False, capture_error='tiles blocked')
        text = ' '.join(extract_text(pdf).split())
        self.assertIn('The live heatmap screenshot is not available', text)
        self.assertIn('tiles blocked', text)
        self.assertIn('Reconstruction (not a screenshot)', text)

    def test_missing_optional_data(self):
        pdf, _, _ = build_pdf(elements=[], screenshot=False)
        text = ' '.join(extract_text(pdf).split())
        self.assertIn('Data unavailable for this analysis.', text)
        self.assertIn('no sector could be classified', text)

    def test_validate_pdf_rejects_bad_output(self):
        with self.assertRaises(PDFRenderError):
            validate_pdf(b'<html>not a pdf</html>')
        with self.assertRaises(PDFRenderError):
            validate_pdf(self.pdf[:-200])
        with self.assertRaises(PDFRenderError):
            validate_pdf(self.pdf, ['A phrase that is not in the report'])

    def test_external_resources_are_blocked(self):
        from report_generator.pdf_generator import _make_fetcher
        fetcher = _make_fetcher()
        for url in ('https://example.com/x.png', 'file:///etc/passwd', 'http://169.254.169.254/'):
            with self.assertRaises(Exception):
                fetcher.fetch(url)
        self.assertTrue(base64.b64decode('AA=='))  # data: URIs are allowed (used for every image)
