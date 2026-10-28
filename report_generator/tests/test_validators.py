import base64

from django.test import SimpleTestCase

from report_generator import validators as v
from report_generator.prompts import STAGE_SCHEMAS

from .fixtures import LAT, LON, png_data_url, request_body


class RequestValidationTests(SimpleTestCase):
    def test_valid_request(self):
        clean = v.validate_report_request(request_body(business_type='Coffee Shop'))
        self.assertEqual(clean['latitude'], LAT)
        self.assertEqual(clean['radius_m'], 2000)
        self.assertEqual(clean['business_type'], 'Coffee Shop')

    def test_missing_location(self):
        with self.assertRaises(v.ValidationError) as ctx:
            v.validate_report_request({'radius_m': 2000})
        self.assertEqual(ctx.exception.code, 'no_location')

    def test_invalid_radius(self):
        for radius in (9999, 'abc', -1):
            with self.assertRaises(v.ValidationError) as ctx:
                v.validate_report_request(request_body(radius_m=radius))
            self.assertEqual(ctx.exception.code, 'invalid_radius')

    def test_out_of_range_and_non_numeric_coordinates(self):
        for loc in ({'latitude': 91, 'longitude': 0}, {'latitude': 'x', 'longitude': 0},
                    {'latitude': float('nan'), 'longitude': 0}, {'latitude': True, 'longitude': 0}):
            with self.assertRaises(v.ValidationError):
                v.validate_report_request(request_body(location=loc))

    def test_business_type_rejects_markup(self):
        with self.assertRaises(v.ValidationError):
            v.validate_report_request(request_body(business_type='<script>alert(1)</script>'))

    def test_client_supplied_analysis_fields_are_ignored(self):
        clean = v.validate_report_request(request_body(revenue=999999, feasible=True, owner_id='someone-else'))
        self.assertNotIn('revenue', clean)
        self.assertNotIn('owner_id', clean)

    def test_name_falls_back_to_coordinates(self):
        clean = v.validate_report_request(request_body(location={'latitude': LAT, 'longitude': LON}))
        self.assertIn('12.97160', clean['name'])


class CaptureMetaTests(SimpleTestCase):
    def test_matching_capture(self):
        meta = v.validate_capture_meta(request_body()['heatmap'], LAT, LON)
        self.assertTrue(meta['captured'])
        self.assertEqual(meta['offset_m'], 0.0)
        self.assertEqual(meta['client_sector_counts'], {'high': 2, 'medium': 1, 'low': 1})

    def test_inconsistent_coordinates_rejected(self):
        heatmap = dict(request_body()['heatmap'], analysed_lat=LAT + 0.01)  # ~1.1 km away
        with self.assertRaises(v.ValidationError) as ctx:
            v.validate_capture_meta(heatmap, LAT, LON)
        self.assertEqual(ctx.exception.code, 'heatmap_mismatch')

    def test_screenshot_without_location_rejected(self):
        with self.assertRaises(v.ValidationError):
            v.validate_capture_meta({'image': png_data_url()}, LAT, LON)

    def test_capture_failure_is_recorded(self):
        meta = v.validate_capture_meta({'capture_error': 'tiles blocked'}, LAT, LON)
        self.assertFalse(meta['captured'])
        self.assertEqual(meta['capture_error'], 'tiles blocked')


class ScreenshotTests(SimpleTestCase):
    def test_valid_png_and_jpeg_are_reencoded_to_png(self):
        for fmt in ('PNG', 'JPEG'):
            data, size = v.decode_screenshot(png_data_url(fmt=fmt), 2 * 1024 * 1024)
            self.assertTrue(data.startswith(b'\x89PNG'))
            self.assertEqual(size, (640, 400))

    def test_not_an_image(self):
        bad = 'data:image/png;base64,' + base64.b64encode(b'not really a png').decode()
        with self.assertRaises(v.ValidationError) as ctx:
            v.decode_screenshot(bad, 1024 * 1024)
        self.assertEqual(ctx.exception.code, 'invalid_image')

    def test_wrong_mime_and_bad_base64(self):
        for bad in ('data:image/gif;base64,R0lGOD', 'data:image/png;base64,@@@@', 'https://evil.example/x.png', 42):
            with self.assertRaises(v.ValidationError):
                v.decode_screenshot(bad, 1024 * 1024)

    def test_oversized_payload(self):
        with self.assertRaises(v.ValidationError) as ctx:
            v.decode_screenshot(png_data_url(), 100)
        self.assertEqual(ctx.exception.code, 'image_too_large')

    def test_dimensions_checked(self):
        with self.assertRaises(v.ValidationError):
            v.decode_screenshot(png_data_url(100, 80), 1024 * 1024)
        with self.assertRaises(v.ValidationError) as ctx:
            v.decode_screenshot(png_data_url(5000, 300), 10 * 1024 * 1024)
        self.assertEqual(ctx.exception.code, 'image_too_large')


class AIOutputValidationTests(SimpleTestCase):
    def test_schema_accepts_valid_and_trims(self):
        payload = {'overview': 'x' * 2000, 'commercial_character': 'ok', 'data_caveats': ['a', 'b', 5, '']}
        clean = v.validate_ai_payload(payload, STAGE_SCHEMAS['location'])
        self.assertEqual(len(clean['overview']), 900)
        self.assertEqual(clean['data_caveats'], ['a', 'b'])

    def test_schema_rejects_missing_or_wrong_types(self):
        for payload in ({}, {'overview': 'a', 'commercial_character': 'b'},
                        {'overview': 3, 'commercial_character': 'b', 'data_caveats': ['c']}, ['not', 'a', 'dict']):
            with self.assertRaises(v.ValidationError):
                v.validate_ai_payload(payload, STAGE_SCHEMAS['location'])

    def test_number_grounding(self):
        evidence = {243567.0, 0.18, 62.0, 2000.0}
        self.assertEqual(v.ungrounded_numbers('About ₹2.4 lakh a month, 18% conversion, 62 rivals within 2,000 m', evidence), [])
        self.assertEqual(v.ungrounded_numbers('Rent is ₹50,000 with a 35% margin', evidence), ['₹50,000', '35%'])
        self.assertEqual(v.ungrounded_numbers('Survey 30 people', evidence, money_only=True), [])
