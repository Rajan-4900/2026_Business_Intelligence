"""
Report generation pipeline – the single entry point used by the dashboard
button and the chatbot (both go through POST /api/reports/generate/).

Generation runs in a background thread inside the web process (no Celery or
Redis): the request returns a report id immediately and the browser polls
the status endpoint. Each stage is recorded only after it has finished.
"""
import logging
import threading
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import close_old_connections, connection
from django.utils import timezone

from . import ai_writer, chart_generator, content, flowchart_generator
from .data_collector import CollectionError, collect_analysis
from .models import Report
from .pdf_generator import PDFRenderError, render_pdf, validate_pdf

logger = logging.getLogger(__name__)

STAGES = [
    ('capture', 'Capturing the heatmap'),
    ('collect', 'Collecting location data'),
    ('crowd', 'Analyzing crowd intensity'),
    ('recommend', 'Preparing business recommendations'),
    ('revenue', 'Calculating revenue scenarios'),
    ('writing', 'Writing report explanations'),
    ('visuals', 'Generating charts and flowcharts'),
    ('pdf', 'Creating PDF'),
    ('validate', 'Validating PDF'),
    ('ready', 'Report ready'),
]
STAGE_KEYS = [k for k, _ in STAGES]
STALE_AFTER = timedelta(minutes=10)
IST = ZoneInfo('Asia/Kolkata')
PLATFORM_NAME = 'Crowd Heatmap & Business Intelligence Platform'
MODEL_TRAINING_ROWS = None  # lazily read from the dataset

_admission_lock = threading.Lock()


class ReportLimitError(Exception):
    def __init__(self, message, status, existing=None):
        super().__init__(message)
        self.status = status
        self.existing = existing


# ---------------------------------------------------------------------------
# Admission: retention, staleness, duplicates and rate limits
# ---------------------------------------------------------------------------

def purge_expired():
    deleted, _ = Report.objects.filter(expires_at__lt=timezone.now()).delete()
    return deleted


def fail_stale():
    """Jobs whose thread died (e.g. the server restarted) are marked failed."""
    cutoff = timezone.now() - STALE_AFTER
    return Report.objects.filter(status__in=[Report.QUEUED, Report.RUNNING], updated_at__lt=cutoff).update(
        status=Report.FAILED, error_message='Report generation was interrupted. Please try again.', screenshot=None)


def create_report(owner_id, request_data, screenshot_png, capture_meta):
    """Admit and queue a report, then start generating it. Raises ReportLimitError."""
    with _admission_lock:
        purge_expired()
        fail_stale()
        active = Report.objects.filter(status__in=[Report.QUEUED, Report.RUNNING])
        existing = active.filter(owner_id=owner_id).first()
        if existing:
            raise ReportLimitError('A report is already being generated for your account.', 409, existing)
        hour_ago = timezone.now() - timedelta(hours=1)
        if Report.objects.filter(owner_id=owner_id, created_at__gte=hour_ago).count() >= settings.REPORT_MAX_PER_HOUR:
            raise ReportLimitError('Hourly report limit reached. Please try again later.', 429)
        if active.count() >= settings.REPORT_MAX_CONCURRENT:
            raise ReportLimitError('The report service is busy. Please try again in a minute.', 429)

        report = Report.objects.create(
            owner_id=owner_id,
            source=request_data['source'],
            status=Report.QUEUED,
            stage='collect',
            completed_stages=['capture'] if screenshot_png else [],
            location_name=request_data['name'],
            latitude=request_data['latitude'],
            longitude=request_data['longitude'],
            radius_m=request_data['radius_m'],
            business_type=request_data['business_type'],
            screenshot=screenshot_png,
            capture_meta=capture_meta,
            expires_at=timezone.now() + timedelta(hours=settings.REPORT_RETENTION_HOURS),
        )
    start(report.id)
    return report


def start(report_id):
    if settings.REPORT_RUN_INLINE:
        run_generation(report_id)
        return
    thread = threading.Thread(target=_thread_main, args=(report_id,), name=f'report-{report_id}', daemon=True)
    thread.start()


def _thread_main(report_id):
    try:
        run_generation(report_id)
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def _mark(report, stage):
    """Record `stage` as finished and the next one as current."""
    if stage not in report.completed_stages:
        report.completed_stages = report.completed_stages + [stage]
    idx = STAGE_KEYS.index(stage)
    report.stage = STAGE_KEYS[idx + 1] if idx + 1 < len(STAGE_KEYS) else stage
    report.save(update_fields=['completed_stages', 'stage', 'status', 'updated_at'])


def run_generation(report_id):
    close_old_connections()
    try:
        report = Report.objects.get(id=report_id)
    except Report.DoesNotExist:
        return
    report.status = Report.RUNNING
    report.save(update_fields=['status', 'updated_at'])
    try:
        pdf, pages, ai_used = _generate(report)
    except CollectionError as exc:
        _fail(report, str(exc))
    except PDFRenderError as exc:
        logger.exception('PDF rendering failed for report %s', report_id)
        _fail(report, 'The PDF could not be created. ' + ('A system dependency (WeasyPrint/Pango) is missing.'
                                                           if 'not available' in str(exc) else 'Please try again.'))
    except Exception:
        logger.exception('Report %s failed', report_id)
        _fail(report, 'Report generation failed unexpectedly. Please try again.')
    else:
        report.pdf = pdf
        report.pdf_size = len(pdf)
        report.page_count = pages
        report.ai_used = ai_used
        report.screenshot = None
        report.status = Report.SUCCEEDED
        report.completed_stages = report.completed_stages + ['ready']
        report.stage = 'ready'
        report.save()


def _fail(report, message):
    report.status = Report.FAILED
    report.error_message = message[:300]
    report.screenshot = None
    report.save(update_fields=['status', 'error_message', 'screenshot', 'updated_at'])


def _generate(report):
    snapshot = collect_analysis(report.latitude, report.longitude, report.location_name, report.radius_m,
                                report.business_type, progress=lambda stage: _mark(report, stage))

    risks = content.risk_register(snapshot)
    texts = ai_writer.write_report_text(snapshot, risks)
    _mark(report, 'writing')

    steps = texts['stages']['roadmap']['data']['steps']
    phases = content.timeline(steps)
    charts = chart_generator.build_all(snapshot, risks, phases)
    flows = flowchart_generator.build_all(snapshot)
    _mark(report, 'visuals')

    context = build_context(report, snapshot, texts, risks, charts, flows)
    pdf, pages = render_pdf(context)
    _mark(report, 'pdf')

    name_probe = ' '.join(report.location_name.split())[:20]
    validate_pdf(pdf, required_phrases=[
        'Business Intelligence Report', 'Executive summary', 'Crowd heatmap analysis', 'Revenue forecast',
        'Implementation roadmap', 'Risk analysis', name_probe])
    _mark(report, 'validate')
    return pdf, pages, texts['ai_status'] != 'unavailable'


def _model_rows():
    global MODEL_TRAINING_ROWS
    if MODEL_TRAINING_ROWS is None:
        from business_intelligence.analysis import _DATASET_PATH
        with open(_DATASET_PATH, encoding='utf-8') as fh:
            MODEL_TRAINING_ROWS = max(0, sum(1 for line in fh if line.strip()) - 1)
    return MODEL_TRAINING_ROWS


def _fmt_time(dt):
    return dt.astimezone(IST).strftime('%d %b %Y, %I:%M %p IST')


def _kpis(s):
    rev, comp, feas, heat, rec = (s.get(k) or {} for k in ('revenue', 'competition', 'feasibility', 'heatmap', 'recommendation'))
    kpis = [{'label': 'Mapped features within 2 km', 'value': f"{s['pois'].get('in_radius', 0):,}",
             'kind': 'observed', 'kind_label': 'Observed', 'note': 'OpenStreetMap'}]
    if not heat.get('placeholder_used'):
        kpis.append({'label': 'High-intensity sectors', 'value': f"{heat['counts']['high']} of 9", 'kind': 'observed',
                     'kind_label': 'Observed', 'note': f"Dominant level: {heat['dominant']}"})
    if rec.get('status') == 'ok':
        kpis.append({'label': 'ML recommendation', 'value': rec['primary'], 'kind': 'estimate',
                     'kind_label': 'Model', 'note': 'Decision-tree label'})
    if feas.get('status') == 'ok':
        kpis.append({'label': f"Feasibility: {content.nice(feas['business_type'])}",
                     'value': 'Feasible' if feas['feasible'] else 'Not feasible', 'kind': 'estimate',
                     'kind_label': 'Rule-based', 'note': 'Platform Go/No-Go rules'})
    if rev.get('status') == 'ok':
        kpis.append({'label': 'Est. gross sales / month', 'value': content.inr(rev['monthly']), 'kind': 'estimate',
                     'kind_label': 'Estimate', 'note': f"Range {content.inr(rev['range']['min'])}–{content.inr(rev['range']['max'])}"})
        kpis.append({'label': 'Potential score', 'value': f"{rev['potential_score']}/100", 'kind': 'estimate',
                     'kind_label': 'Estimate', 'note': 'Revenue-engine index, not a probability'})
    if comp.get('status') == 'ok':
        kpis.append({'label': 'Competitors within 1 km', 'value': str(comp['within_1000_m']), 'kind': 'observed',
                     'kind_label': 'Observed', 'note': f"{comp['count']} within 2 km"})
    return kpis


def build_context(report, snapshot, texts, risks, charts, flows):
    from business_intelligence.analysis import HIGH_SECTOR_MIN_POIS, MEDIUM_SECTOR_MIN_POIS
    from datetime import datetime

    now = timezone.now()
    collected = datetime.fromisoformat(snapshot['collected_at'])
    capture = dict(report.capture_meta or {})
    if capture.get('captured_at_ms'):
        capture['captured_at_local'] = _fmt_time(datetime.fromtimestamp(capture['captured_at_ms'] / 1000, tz=IST))
    client_counts = capture.get('client_sector_counts')
    if client_counts and not snapshot['heatmap'].get('placeholder_used'):
        server_counts = snapshot['heatmap']['counts']
        capture['counts_differ'] = any(client_counts[k] != server_counts[k] for k in ('high', 'medium', 'low'))

    heatmap_image = None
    if report.screenshot:
        import base64
        heatmap_image = 'data:image/png;base64,' + base64.b64encode(bytes(report.screenshot)).decode('ascii')

    top_types = snapshot['pois'].get('top_types') or []
    half = (len(top_types) + 1) // 2
    top_type_rows = [(top_types[i], top_types[i + half] if i + half < len(top_types) else None) for i in range(half)]

    ranked = sorted([c for c in snapshot.get('candidates') or [] if c.get('potential_score') is not None],
                    key=lambda c: c['potential_score'], reverse=True)
    roadmap = content.default_roadmap(snapshot.get('target_business'))

    return {
        'meta': {
            'platform': PLATFORM_NAME,
            'location_name': report.location_name,
            'latitude': report.latitude,
            'longitude': report.longitude,
            'radius_m': report.radius_m,
            'business': content.nice(snapshot.get('target_business')),
            'requested_business': report.business_type,
            'generated_at_local': _fmt_time(now),
            'generated_at_utc': now.strftime('%Y-%m-%d %H:%M'),
            'collected_at_local': _fmt_time(collected),
            'reference': str(report.id)[:8].upper(),
            'ai_message': texts['ai_message'],
        },
        's': snapshot,
        't': texts['stages'],
        'kpis': _kpis(snapshot),
        'charts': charts,
        'flows': flows,
        'risks': risks,
        'checklist': content.CHECKLIST,
        'capture': capture,
        'heatmap_image': heatmap_image,
        'top_type_rows': top_type_rows,
        'ranked_candidates': ranked,
        'group_label': roadmap['group_label'],
        'model_rows': _model_rows(),
        'ring_width': round(report.radius_m / 3),
        'thresholds': {'high': HIGH_SECTOR_MIN_POIS, 'medium': MEDIUM_SECTOR_MIN_POIS,
                       'high_minus_one': HIGH_SECTOR_MIN_POIS - 1},
    }


# ---------------------------------------------------------------------------
# Status payload
# ---------------------------------------------------------------------------

def status_payload(report):
    done = set(report.completed_stages or [])
    stages = []
    for key, label in STAGES:
        if key == 'capture' and key not in done:
            state = 'skipped'
        elif key in done:
            state = 'done'
        elif report.status == Report.FAILED and key == report.stage:
            state = 'failed'
        elif report.status in (Report.QUEUED, Report.RUNNING) and key == report.stage:
            state = 'active'
        else:
            state = 'pending'
        stages.append({'key': key, 'label': label, 'state': state})
    payload = {
        'success': True,
        'report_id': str(report.id),
        'status': report.status,
        'stage': report.stage,
        'stages': stages,
        'location': report.location_name,
        'heatmap_captured': 'capture' in done,
        'created_at': report.created_at.isoformat(),
        'expires_at': report.expires_at.isoformat(),
    }
    if report.status == Report.FAILED:
        payload['error'] = report.error_message
    if report.status == Report.SUCCEEDED:
        payload.update({'download_url': f'/api/reports/{report.id}/download/', 'page_count': report.page_count,
                        'size_bytes': report.pdf_size, 'ai_used': report.ai_used})
    return payload
