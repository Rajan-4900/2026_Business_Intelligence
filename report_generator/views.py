import json
import logging
import time

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from . import services
from .auth import supabase_user_required
from .models import Report
from .validators import ValidationError, decode_screenshot, validate_capture_meta, validate_report_request

logger = logging.getLogger(__name__)


def _error(message, status, code=None, **extra):
    body = {'success': False, 'error': message, **extra}
    if code:
        body['code'] = code
    return JsonResponse(body, status=status)


def _owned_report(request, report_id):
    """Look up by id *and* owner, so another user's id is indistinguishable from a missing one."""
    return Report.objects.filter(id=report_id, owner_id=request.report_owner_id).first()


@require_POST
@supabase_user_required
def generate_report(request):
    """
    Start a report for the selected location. Body:
      {location: {name, latitude, longitude}, radius_m, business_type?, source?,
       heatmap: {image?, capture_error?, analysed_lat, analysed_lon, center_lat, center_lon, zoom,
                 sector_counts, captured_at}}
    Analysis data is recomputed on the server; nothing numeric is taken from the client
    except the coordinates used to check the screenshot belongs to this location.
    """
    try:
        data = json.loads(request.body or b'{}')
    except RequestDataTooBig:
        return _error('The heatmap screenshot is too large.', 413, 'image_too_large')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error('Invalid JSON', 400, 'invalid_json')

    try:
        cleaned = validate_report_request(data)
        capture = validate_capture_meta(cleaned['heatmap'], cleaned['latitude'], cleaned['longitude'])
        screenshot = None
        if cleaned['heatmap'].get('image'):
            screenshot, size = decode_screenshot(cleaned['heatmap']['image'], settings.REPORT_SCREENSHOT_MAX_BYTES)
            capture['width'], capture['height'] = size
        captured_at = cleaned['heatmap'].get('captured_at')
        now_ms = time.time() * 1000
        if (screenshot and isinstance(captured_at, (int, float)) and not isinstance(captured_at, bool)
                and now_ms - 3_600_000 <= captured_at <= now_ms + 300_000):
            capture['captured_at_ms'] = int(captured_at)
    except ValidationError as exc:
        status = {'image_too_large': 413, 'heatmap_mismatch': 409}.get(exc.code, 400)
        return _error(str(exc), status, exc.code)

    try:
        report = services.create_report(request.report_owner_id, cleaned, screenshot, capture)
    except services.ReportLimitError as exc:
        extra = {}
        if exc.existing is not None:
            extra['report_id'] = str(exc.existing.id)
            extra['status_url'] = f'/api/reports/{exc.existing.id}/status/'
        return _error(str(exc), exc.status, 'busy' if exc.status == 409 else 'rate_limited', **extra)

    report.refresh_from_db()
    payload = services.status_payload(report)
    payload['status_url'] = f'/api/reports/{report.id}/status/'
    return JsonResponse(payload, status=202)


@require_GET
@supabase_user_required
def report_status(request, report_id):
    report = _owned_report(request, report_id)
    if report is None:
        return _error('Report not found', 404, 'not_found')
    return JsonResponse(services.status_payload(report))


@require_GET
@supabase_user_required
def download_report(request, report_id):
    report = _owned_report(request, report_id)
    if report is None:
        return _error('Report not found', 404, 'not_found')
    if report.status != Report.SUCCEEDED or not report.pdf:
        return _error('Report is not ready', 409, 'not_ready')
    filename = f'business-report-{report.created_at:%Y%m%d-%H%M}.pdf'
    response = HttpResponse(bytes(report.pdf), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Cache-Control'] = 'no-store, private'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
