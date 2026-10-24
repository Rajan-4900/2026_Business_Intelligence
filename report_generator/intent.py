"""
Recognises chat messages that ask for a PDF report to be generated.

A request needs both a "make/give me" verb and the word report or PDF, so
questions *about* reports ("what does the report include?", "how do I make
a report?") are left to the normal chatbot.

static/js/report-generator.js (looksLikeReportRequest) mirrors this pattern
only to stop the map-command parser from acting on the same message; the
server decides.
"""
import re

_REQUEST = re.compile(
    r'\b(generate|create|make|build|prepare|produce|export|download|give\s+me|get\s+me|send\s+me|'
    r'i\s+(?:want|need|would\s+like))\b.{0,80}?\b(report|pdf)\b',
    re.IGNORECASE | re.DOTALL)
_QUESTION_ABOUT = re.compile(r'^\s*(how|what|why|when|where|which|explain|tell\s+me\s+about)\b', re.IGNORECASE)


def is_report_request(message):
    text = (message or '').strip()
    if not text or len(text) > 500:
        return False
    if _QUESTION_ABOUT.match(text):
        return False
    return bool(_REQUEST.search(text))


def chat_response(client_location):
    """
    Chat reply for a report request. The browser then runs the same
    generation flow as the dashboard button (it holds the map to capture and
    the user's session), which calls POST /api/reports/generate/.
    """
    loc = client_location if isinstance(client_location, dict) else None
    lat = lon = None
    if loc:
        try:
            lat = float(loc.get('lat') if loc.get('lat') is not None else loc.get('latitude'))
            lon = float(loc.get('lon') if loc.get('lon') is not None else loc.get('lng', loc.get('longitude')))
        except (TypeError, ValueError):
            lat = lon = None
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return {
            'success': True,
            'message': ('📄 I can generate a detailed PDF report, but no location is selected yet. '
                        'Search for a place or click the map on the dashboard, then ask again.'),
            'structured_actions': [{'intent': 'open_dashboard', 'label': '📈 Open Dashboard'}],
        }
    name = str(loc.get('name') or '').strip()[:120] or f'{lat:.4f}, {lon:.4f}'
    return {
        'success': True,
        'message': (f'📄 Generating a detailed PDF report for **{name}**. I will capture the heatmap and '
                    'run the analysis; progress appears below and on the dashboard.'),
        'structured_actions': [{'intent': 'generate_report', 'label': '📄 Generate PDF report', 'auto_run': True,
                                'location': name}],
    }
