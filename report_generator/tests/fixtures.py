"""
Deterministic Overpass-style fixture around a point in Bengaluru, shaped like
real responses (nodes with lat/lon, ways with center, tag mixes from
amenity/shop/building/highway/public_transport). No network access.
"""
import base64
import io
import math
from contextlib import contextmanager
from unittest.mock import patch

from PIL import Image

LAT, LON = 12.9716, 77.5946
NAME = 'MG Road, Bengaluru'


def _point(i, ring_m, bearing_deg):
    d_lat = ring_m * math.cos(math.radians(bearing_deg)) / 110540.0
    d_lon = ring_m * math.sin(math.radians(bearing_deg)) / (111320.0 * math.cos(math.radians(LAT)))
    return LAT + d_lat, LON + d_lon


def overpass_elements():
    """~150 features: a dense commercial core, a medium ring and a sparse edge."""
    els = []
    i = 0

    def add(ring, bearing, tags, way=False):
        nonlocal i
        i += 1
        lat, lon = _point(i, ring, bearing)
        el = {'type': 'way' if way else 'node', 'id': 1000 + i, 'tags': tags}
        if way:
            el['center'] = {'lat': lat, 'lon': lon}
        else:
            el['lat'], el['lon'] = lat, lon
        els.append(el)

    for k in range(24):   # dense core, east wedge
        add(150 + 12 * k, 60 + (k % 9) * 10, {'amenity': 'cafe', 'name': f'Cafe {k}'} if k % 4 == 0 else
            {'shop': 'clothes', 'name': f'Store {k}'} if k % 4 == 1 else
            {'amenity': 'restaurant', 'name': f'Restaurant {k}'} if k % 4 == 2 else {'building': 'commercial'},
            way=(k % 4 == 3))
    for k in range(18):   # medium density, north-west wedge
        add(900 + 15 * k, 300 + (k % 6) * 8, {'shop': 'supermarket', 'name': f'Mart {k}'} if k % 3 == 0 else
            {'building': 'apartments'} if k % 3 == 1 else {'highway': 'bus_stop'}, way=(k % 3 == 1))
    for k in range(9):    # medium density, south-west wedge
        add(800 + 40 * k, 200 + (k % 5) * 10, {'amenity': 'pharmacy', 'name': f'Pharmacy {k}'} if k % 3 == 0 else
            {'amenity': 'school'} if k % 3 == 1 else {'highway': 'residential'}, way=(k % 3 == 2))
    for k in range(3):    # sparse edge
        add(1700 + 50 * k, 100 + 5 * k, {'amenity': 'bank', 'name': f'Bank {k}'})
    add(3500, 45, {'shop': 'bakery'})  # outside the 2 km radius
    els.append({'type': 'node', 'id': 99, 'tags': {'amenity': 'cafe'}})  # no coordinates
    return els


@contextmanager
def fake_overpass(elements=None, error=None):
    """Patch the shared Overpass helper used by the views and the report."""
    data = None if error else {'elements': overpass_elements() if elements is None else elements}
    # views.py imports the helper by name, so both references are patched.
    with patch('business_intelligence.analysis._run_overpass_query', return_value=(data, error)) as m, \
            patch('business_intelligence.views._run_overpass_query', return_value=(data, error)):
        yield m


@contextmanager
def signed_in(user_id='user-aaaaaaaa-1111'):
    with patch('report_generator.auth.verify_supabase_token', return_value=user_id):
        yield


def auth_header(token='t' * 40):
    return {'HTTP_AUTHORIZATION': f'Bearer {token}'}


def png_data_url(width=640, height=400, color=(30, 120, 200), fmt='PNG'):
    img = Image.new('RGB', (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    mime = 'jpeg' if fmt == 'JPEG' else 'png'
    return f'data:image/{mime};base64,' + base64.b64encode(buf.getvalue()).decode()


def request_body(**overrides):
    body = {
        'location': {'name': NAME, 'latitude': LAT, 'longitude': LON},
        'radius_m': 2000,
        'business_type': '',
        'scope': 'full',
        'source': 'dashboard',
        'heatmap': {
            'image': png_data_url(),
            'analysed_lat': LAT, 'analysed_lon': LON,
            'center_lat': LAT, 'center_lon': LON, 'zoom': 14,
            'sector_counts': {'high': 2, 'medium': 1, 'low': 1},
        },
    }
    body.update(overrides)
    return body
