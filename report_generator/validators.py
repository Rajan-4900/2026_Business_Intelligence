"""
Validation for report requests, uploaded heatmap screenshots, and the
structured text Gemini returns.

Nothing the browser sends is trusted as analysis data: only the location,
an optional business type, and the screenshot (with the coordinates it was
taken at) are accepted. Revenue, scores and feasibility are recomputed on
the server.
"""
import base64
import binascii
import io
import math
import re

from PIL import Image, UnidentifiedImageError

from business_intelligence.analysis import HEATMAP_RADIUS_M

SUPPORTED_RADII_M = (2000, 5000, HEATMAP_RADIUS_M)
# How far (metres) the analysed heatmap centre may be from the requested
# location before we refuse to pair that screenshot with this report.
MAX_CAPTURE_OFFSET_M = 30.0

MIN_IMAGE_SIZE = (300, 200)
MAX_IMAGE_SIZE = (4096, 4096)

_CONTROL_CHARS = re.compile(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]')
_BUSINESS_RE = re.compile(r"^[A-Za-z0-9 _&'./-]{1,60}$")
_DATA_URL_RE = re.compile(r'^data:image/(png|jpeg);base64,([A-Za-z0-9+/=\s]+)$')


class ValidationError(Exception):
    def __init__(self, message, code='invalid'):
        super().__init__(message)
        self.code = code


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def clean_text(value, max_len):
    text = _CONTROL_CHARS.sub('', str(value or '')).strip()
    return text[:max_len]


def _number(value, name):
    if isinstance(value, bool):
        raise ValidationError(f'{name} must be a number')
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f'{name} must be a number')
    if not math.isfinite(num):
        raise ValidationError(f'{name} must be a finite number')
    return num


def validate_coordinates(lat, lon):
    lat = _number(lat, 'latitude')
    lon = _number(lon, 'longitude')
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValidationError('Coordinates out of range')
    return lat, lon


def validate_business_type(value):
    text = clean_text(value, 60)
    if not text:
        return ''
    if not _BUSINESS_RE.match(text):
        raise ValidationError('business_type contains unsupported characters')
    return text


def validate_report_request(data):
    """
    Validate the JSON body of POST /api/reports/generate/.
    Returns a dict with clean values; screenshot bytes are validated separately.
    """
    if not isinstance(data, dict):
        raise ValidationError('Expected a JSON object')
    location = data.get('location')
    if not isinstance(location, dict):
        raise ValidationError('location is required. Select a location on the map first.', 'no_location')
    lat, lon = validate_coordinates(location.get('latitude'), location.get('longitude'))
    name = clean_text(location.get('name'), 200) or f'{lat:.5f}, {lon:.5f}'

    radius = data.get('radius_m', HEATMAP_RADIUS_M)
    try:
        radius = int(radius)
    except (TypeError, ValueError):
        raise ValidationError('radius_m must be an integer', 'invalid_radius')
    if radius not in SUPPORTED_RADII_M:
        raise ValidationError(
            f'Unsupported analysis radius {radius} m. The heatmap is computed for {HEATMAP_RADIUS_M} m.',
            'invalid_radius')

    scope = data.get('scope', 'full')
    if scope != 'full':
        raise ValidationError('Only the "full" report scope is supported')

    source = data.get('source', 'dashboard')
    if source not in ('dashboard', 'chat'):
        source = 'dashboard'

    heatmap = data.get('heatmap')
    if heatmap is not None and not isinstance(heatmap, dict):
        raise ValidationError('heatmap must be an object')

    return {
        'name': name,
        'latitude': lat,
        'longitude': lon,
        'radius_m': radius,
        'business_type': validate_business_type(data.get('business_type')),
        'source': source,
        'heatmap': heatmap or {},
    }


def validate_capture_meta(heatmap, lat, lon):
    """
    Check that the screenshot was taken of the heatmap analysed for this exact
    location. Returns clean metadata. Raises ValidationError('heatmap_mismatch')
    when the map on screen belongs to a different location.
    """
    meta = {
        'captured': bool(heatmap.get('image')),
        'capture_error': clean_text(heatmap.get('capture_error'), 200),
    }
    if heatmap.get('analysed_lat') is None or heatmap.get('analysed_lon') is None:
        if meta['captured']:
            raise ValidationError('The screenshot is missing the location it was analysed for.', 'heatmap_mismatch')
        return meta

    a_lat, a_lon = validate_coordinates(heatmap.get('analysed_lat'), heatmap.get('analysed_lon'))
    offset = haversine_m(lat, lon, a_lat, a_lon)
    if offset > MAX_CAPTURE_OFFSET_M:
        raise ValidationError(
            'The heatmap on screen was analysed for a different location than the one selected. '
            'Re-run the heatmap for the selected location and try again.', 'heatmap_mismatch')
    meta.update({'analysed_lat': a_lat, 'analysed_lon': a_lon, 'offset_m': round(offset, 1)})

    for key in ('center_lat', 'center_lon', 'zoom'):
        if heatmap.get(key) is not None:
            meta[key] = round(_number(heatmap.get(key), key), 6)
    counts = heatmap.get('sector_counts')
    if isinstance(counts, dict):
        clean_counts = {}
        for level in ('high', 'medium', 'low'):
            try:
                clean_counts[level] = max(0, min(100, int(counts.get(level, 0))))
            except (TypeError, ValueError):
                clean_counts[level] = 0
        meta['client_sector_counts'] = clean_counts
    return meta


def decode_screenshot(data_url, max_bytes):
    """
    Decode and validate a base64 PNG/JPEG data URL. The image is re-encoded
    to PNG so only pixels (no metadata or trailing payloads) are stored.
    Returns (png_bytes, (width, height)).
    """
    if not isinstance(data_url, str):
        raise ValidationError('Screenshot must be a data URL string', 'invalid_image')
    # Reject before parsing when the payload is obviously too large.
    if len(data_url) > max_bytes * 4 // 3 + 200:
        raise ValidationError('Screenshot is too large', 'image_too_large')
    match = _DATA_URL_RE.match(data_url.strip())
    if not match:
        raise ValidationError('Screenshot must be a PNG or JPEG data URL', 'invalid_image')
    encoded = re.sub(r'\s', '', match.group(2))
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise ValidationError('Screenshot is not valid base64', 'invalid_image')
    if len(raw) > max_bytes:
        raise ValidationError('Screenshot is too large', 'image_too_large')

    try:
        with Image.open(io.BytesIO(raw)) as probe:
            fmt = probe.format
            width, height = probe.size
            if fmt not in ('PNG', 'JPEG'):
                raise ValidationError('Screenshot must be PNG or JPEG', 'invalid_image')
            if width < MIN_IMAGE_SIZE[0] or height < MIN_IMAGE_SIZE[1]:
                raise ValidationError('Screenshot is too small to be a map capture', 'invalid_image')
            if width > MAX_IMAGE_SIZE[0] or height > MAX_IMAGE_SIZE[1]:
                raise ValidationError('Screenshot dimensions are too large', 'image_too_large')
            probe.verify()
        with Image.open(io.BytesIO(raw)) as img:
            img = img.convert('RGB')
            out = io.BytesIO()
            img.save(out, format='PNG', optimize=True)
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
        raise ValidationError('Screenshot could not be read as an image', 'invalid_image')
    return out.getvalue(), (width, height)


# ---------------------------------------------------------------------------
# AI output validation
# ---------------------------------------------------------------------------

def validate_ai_payload(payload, schema):
    """
    Check Gemini's JSON against a small schema and return a cleaned copy.

    schema maps field -> spec, where spec is one of
      ('str', max_len)
      ('list', max_items, max_len)                list of strings
      ('objects', max_items, {field: spec, ...})  list of objects
      ('int', lo, hi)
    Every field is required. Raises ValidationError on any mismatch.
    """
    if not isinstance(payload, dict):
        raise ValidationError('AI output is not a JSON object', 'ai_invalid')
    clean = {}
    for field, spec in schema.items():
        if field not in payload:
            raise ValidationError(f'AI output is missing "{field}"', 'ai_invalid')
        clean[field] = _check_value(payload[field], spec, field)
    return clean


def _check_value(value, spec, field):
    kind = spec[0]
    if kind == 'str':
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f'"{field}" must be non-empty text', 'ai_invalid')
        return clean_text(value, spec[1])
    if kind == 'int':
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValidationError(f'"{field}" must be a number', 'ai_invalid')
        return int(max(spec[1], min(spec[2], round(value))))
    if kind == 'list':
        if not isinstance(value, list) or not value:
            raise ValidationError(f'"{field}" must be a non-empty list', 'ai_invalid')
        items = [clean_text(v, spec[2]) for v in value[:spec[1]] if isinstance(v, str) and v.strip()]
        if not items:
            raise ValidationError(f'"{field}" has no usable items', 'ai_invalid')
        return items
    if kind == 'objects':
        if not isinstance(value, list) or not value:
            raise ValidationError(f'"{field}" must be a non-empty list', 'ai_invalid')
        return [validate_ai_payload(item, spec[2]) for item in value[:spec[1]]]
    raise ValueError(f'Unknown schema kind {kind}')


_NUMBER_RE = re.compile(
    r'(₹|rs\.?\s?|inr\s?)?(?<![\w.])(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*'
    r'(%|percent|lakh|lakhs|crore|crores|k\b|thousand)?',
    re.IGNORECASE)
_MULTIPLIERS = {'lakh': 1e5, 'lakhs': 1e5, 'crore': 1e7, 'crores': 1e7, 'k': 1e3, 'thousand': 1e3}


def collect_numbers(obj, out=None):
    """All numeric leaves in a nested structure (bools excluded)."""
    if out is None:
        out = set()
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        if math.isfinite(obj):
            out.add(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            collect_numbers(v, out)
    elif isinstance(obj, str):
        for m in _NUMBER_RE.finditer(obj):
            out.add(float(m.group(2).replace(',', '')))
    return out


def ungrounded_numbers(text, evidence_numbers, money_only=False):
    """
    Numbers >= 10 in `text` that do not match any evidence number (within
    rounding tolerance). Small numbers (step counts, "3 sectors") are allowed.
    Percentages also match evidence fractions (0.18 -> 18%). With money_only,
    only rupee amounts, percentages and lakh/crore figures are checked.
    """
    bad = []
    for m in _NUMBER_RE.finditer(text or ''):
        currency = m.group(1)
        unit = (m.group(3) or '').lower()
        if money_only and not currency and not unit:
            continue
        value = float(m.group(2).replace(',', '')) * _MULTIPLIERS.get(unit, 1)
        if value < 10:
            continue
        candidates = [value]
        if unit in ('%', 'percent'):
            candidates.append(value / 100.0)
        if not any(_close(c, e) for c in candidates for e in evidence_numbers):
            bad.append(m.group(0).strip())
    return bad


def _close(value, evidence):
    if evidence == 0:
        return abs(value) < 0.5
    rel = 0.05 if abs(evidence) >= 1000 else 0.02
    # Fractions (e.g. 0.18 conversion) must match closely; whole numbers may be rounded.
    floor = 0.5 if abs(evidence) >= 10 else 0.006
    return abs(value - evidence) <= max(floor, rel * abs(evidence))
