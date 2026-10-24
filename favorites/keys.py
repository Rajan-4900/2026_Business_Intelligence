import hashlib
import re

PLACE_KEY_RE = re.compile(r'^(osm:[a-z]{1,10}:\d{1,20}|geo:-?\d{1,3}\.\d{4}:-?\d{1,3}\.\d{4}:[a-z0-9-]{0,60}|geo:[0-9a-f]{40})$')


def make_place_key(osm_type, osm_id, name, latitude, longitude):
    """
    Stable identity for a place, shared by every user so favorites can be
    aggregated into "popular" counts. Prefers the OpenStreetMap id; falls back
    to a rounded coordinate + name slug (~11 m precision).

    NOTE: static/js/favorites.js (placeKey) must stay in sync with this.
    """
    if osm_type and osm_id:
        return f'osm:{osm_type}:{osm_id}'
    slug = re.sub(r'[^a-z0-9]+', '-', (name or '').lower()).strip('-')[:60]
    raw = f'geo:{latitude:.4f}:{longitude:.4f}:{slug}'
    return raw if len(raw) <= 120 else 'geo:' + hashlib.sha1(raw.encode()).hexdigest()
