import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from report_generator.auth import AuthError, verify_supabase_token
from report_generator.models import Report
from report_generator.pdf_generator import extract_text

from .fixtures import LAT, LON, NAME, auth_header, fake_overpass, request_body, signed_in

GENERATE = '/api/reports/generate/'


@override_settings(REPORT_RUN_INLINE=True, REPORT_AI_ENABLED=False, REPORT_MAX_PER_HOUR=10, REPORT_MAX_CONCURRENT=2)
class ReportAPITests(TestCase):
    def post(self, body, client=None, user='user-aaaaaaaa-1111', **extra):
        client = client or self.client
        with signed_in(user), fake_overpass():
            return client.post(GENERATE, data=json.dumps(body), content_type='application/json',
                               **auth_header(), **extra)

    def get(self, url, user='user-aaaaaaaa-1111'):
        with signed_in(user):
            return self.client.get(url, **auth_header())

    # --- happy path ---------------------------------------------------
    def test_generate_status_and_download(self):
        resp = self.post(request_body(business_type='cafe'))
        self.assertEqual(resp.status_code, 202, resp.content)
        report_id = resp.json()['report_id']

        status = self.get(f'/api/reports/{report_id}/status/').json()
        self.assertEqual(status['status'], 'succeeded', status)
        states = {s['key']: s['state'] for s in status['stages']}
        self.assertTrue(all(v == 'done' for v in states.values()), states)
        self.assertTrue(status['heatmap_captured'])

        pdf = self.get(f'/api/reports/{report_id}/download/')
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', pdf['Content-Disposition'])
        self.assertNotIn('MG', pdf['Content-Disposition'])  # no location in the filename
        self.assertEqual(pdf['Cache-Control'], 'no-store, private')
        body = pdf.content
        self.assertTrue(body.startswith(b'%PDF-'))

        # Screenshot and financial figures belong to the same, requested location.
        text = ' '.join(extract_text(body).split())
        self.assertIn(NAME, text)
        self.assertIn('Screenshot of the live heatmap for MG Road, Bengaluru', text)
        report = Report.objects.get(id=report_id)
        self.assertIsNone(report.screenshot)  # cleared once the PDF exists
        self.assertEqual((report.latitude, report.longitude), (LAT, LON))

    def test_capture_failure_still_generates_with_warning(self):
        body = request_body(heatmap={'capture_error': 'The browser blocked reading the map image'})
        resp = self.post(body)
        self.assertEqual(resp.status_code, 202)
        status = self.get(f"/api/reports/{resp.json()['report_id']}/status/").json()
        self.assertEqual(status['status'], 'succeeded')
        self.assertFalse(status['heatmap_captured'])
        self.assertEqual({s['key']: s['state'] for s in status['stages']}['capture'], 'skipped')
        pdf = self.get(f"/api/reports/{resp.json()['report_id']}/download/").content
        self.assertIn('The browser blocked reading the map image', ' '.join(extract_text(pdf).split()))

    def test_overpass_failure_marks_report_failed(self):
        with signed_in(), fake_overpass(error='Overpass API timeout'):
            resp = self.client.post(GENERATE, data=json.dumps(request_body()), content_type='application/json', **auth_header())
        self.assertEqual(resp.status_code, 202)
        status = self.get(f"/api/reports/{resp.json()['report_id']}/status/").json()
        self.assertEqual(status['status'], 'failed')
        self.assertIn('OpenStreetMap data could not be retrieved', status['error'])
        self.assertNotIn('Traceback', status['error'])
        self.assertEqual(self.get(f"/api/reports/{resp.json()['report_id']}/download/").status_code, 409)

    # --- input validation ------------------------------------------------
    def test_invalid_payloads(self):
        cases = [
            ({}, 400, 'no_location'),
            (request_body(radius_m=5000), 400, 'invalid_radius'),
            (request_body(location={'latitude': 'abc', 'longitude': 1}), 400, None),
            (request_body(heatmap=dict(request_body()['heatmap'], image='data:image/png;base64,AAAA')), 400, 'invalid_image'),
            (request_body(heatmap=dict(request_body()['heatmap'], analysed_lat=LAT + 0.05)), 409, 'heatmap_mismatch'),
        ]
        for body, status, code in cases:
            resp = self.post(body)
            self.assertEqual(resp.status_code, status, (body.keys(), resp.content))
            if code:
                self.assertEqual(resp.json()['code'], code)
        self.assertEqual(Report.objects.count(), 0)

    def test_invalid_json(self):
        with signed_in():
            resp = self.client.post(GENERATE, data='{not json', content_type='application/json', **auth_header())
        self.assertEqual(resp.status_code, 400)

    @override_settings(REPORT_SCREENSHOT_MAX_BYTES=1000)
    def test_oversized_screenshot(self):
        resp = self.post(request_body())
        self.assertEqual(resp.status_code, 413)

    @override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=500)
    def test_request_body_over_django_limit(self):
        resp = self.post(request_body())
        self.assertEqual(resp.status_code, 413)

    # --- authentication and authorisation -----------------------------
    def test_requires_bearer_token(self):
        resp = self.client.post(GENERATE, data=json.dumps(request_body()), content_type='application/json')
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(self.client.get(f'/api/reports/{uuid.uuid4()}/status/').status_code, 401)

    def test_rejected_token(self):
        with patch('report_generator.auth.verify_supabase_token', side_effect=AuthError(401, 'Invalid or expired session.')):
            resp = self.client.post(GENERATE, data=json.dumps(request_body()), content_type='application/json',
                                    **auth_header())
        self.assertEqual(resp.status_code, 401)

    def test_cross_user_access_is_not_found(self):
        report_id = self.post(request_body()).json()['report_id']
        for url in (f'/api/reports/{report_id}/status/', f'/api/reports/{report_id}/download/'):
            resp = self.get(url, user='user-bbbbbbbb-2222')
            self.assertEqual(resp.status_code, 404)
            self.assertEqual(resp.json()['code'], 'not_found')

    def test_invalid_report_ids(self):
        self.assertEqual(self.get(f'/api/reports/{uuid.uuid4()}/download/').status_code, 404)
        self.assertEqual(self.get('/api/reports/123/download/').status_code, 404)
        self.assertEqual(self.get('/api/reports/..%2F..%2Fetc%2Fpasswd/download/').status_code, 404)

    def test_csrf_is_enforced(self):
        csrf_client = Client(enforce_csrf_checks=True)
        resp = self.post(request_body(), client=csrf_client)
        self.assertEqual(resp.status_code, 403)
        csrf_client.get('/dashboard/')
        token = csrf_client.cookies['csrftoken'].value
        resp = self.post(request_body(), client=csrf_client, HTTP_X_CSRFTOKEN=token)
        self.assertEqual(resp.status_code, 202)

    def test_supabase_token_verification(self):
        class Resp:
            def __init__(self, status, body):
                self.status_code, self._body = status, body

            def json(self):
                return self._body
        with patch('report_generator.auth.requests.get', return_value=Resp(200, {'id': 'abcd1234-ef56-7890'})):
            self.assertEqual(verify_supabase_token('x' * 40), 'abcd1234-ef56-7890')
        with patch('report_generator.auth.requests.get', return_value=Resp(401, {})):
            with self.assertRaises(AuthError) as ctx:
                verify_supabase_token('y' * 40)
            self.assertEqual(ctx.exception.status, 401)

    # --- abuse prevention and retention ------------------------------
    def test_duplicate_request_returns_existing_job(self):
        running = Report.objects.create(owner_id='user-aaaaaaaa-1111', location_name=NAME, latitude=LAT, longitude=LON,
                                        radius_m=2000, status=Report.RUNNING, expires_at=timezone.now() + timedelta(hours=1))
        resp = self.post(request_body())
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()['report_id'], str(running.id))

    @override_settings(REPORT_MAX_PER_HOUR=1)
    def test_hourly_limit(self):
        self.assertEqual(self.post(request_body()).status_code, 202)
        self.assertEqual(self.post(request_body()).status_code, 429)

    def test_expired_reports_are_purged_and_stale_jobs_failed(self):
        old = Report.objects.create(owner_id='u-12345678', location_name='x', latitude=1, longitude=1, radius_m=2000,
                                    status=Report.SUCCEEDED, expires_at=timezone.now() - timedelta(minutes=1))
        stale = Report.objects.create(owner_id='u-12345678', location_name='x', latitude=1, longitude=1, radius_m=2000,
                                      status=Report.RUNNING, expires_at=timezone.now() + timedelta(hours=1))
        Report.objects.filter(id=stale.id).update(updated_at=timezone.now() - timedelta(minutes=30))
        call_command('cleanup_reports', stdout=open('/dev/null', 'w'))
        self.assertFalse(Report.objects.filter(id=old.id).exists())
        self.assertEqual(Report.objects.get(id=stale.id).status, Report.FAILED)
