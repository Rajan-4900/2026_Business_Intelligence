"""
Popularity + personalisation ranking for favorite places.

Pure functions over plain dicts (no ORM) so the maths is easy to test.

Each candidate place is scored from four signals in [0, 1]:

  popularity  time-decayed number of distinct users who saved it, log-scaled
              so one viral place doesn't flatten everything else
  affinity    how much *this* user likes the place's category, learned from
              their own (time-decayed) favorites
  proximity   exp(-distance / PROXIMITY_SCALE_KM) from an anchor: the
              caller's current map position, else the centroid of the
              user's favorites
  quality     the revenue engine's average location score, 0-100 -> 0-1

Signals that can't be computed (no history -> no affinity, no anchor -> no
proximity) are dropped and the remaining weights renormalised, which gives a
sensible "trending near you" cold start for new users.
"""
import math
from collections import defaultdict
from datetime import datetime, timezone

HALF_LIFE_DAYS = 45.0
PROXIMITY_SCALE_KM = 5.0
WEIGHTS = {'popularity': 0.35, 'affinity': 0.30, 'proximity': 0.20, 'quality': 0.15}


def decay(created_at, now):
    age_days = max((now - created_at).total_seconds(), 0) / 86400.0
    return 0.5 ** (age_days / HALF_LIFE_DAYS)


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(a)))


def category_affinity(user_rows, now):
    """{category: share in (0, 1]} where the user's top category == 1.0."""
    totals = defaultdict(float)
    for r in user_rows:
        if r['category']:
            totals[r['category']] += decay(r['created_at'], now)
    top = max(totals.values(), default=0)
    return {c: w / top for c, w in totals.items()} if top else {}


def centroid(user_rows):
    if not user_rows:
        return None
    return (sum(r['latitude'] for r in user_rows) / len(user_rows),
            sum(r['longitude'] for r in user_rows) / len(user_rows))


def aggregate_community(rows, now):
    """Collapse every user's favorites into one record per place_key."""
    places = {}
    for r in rows:
        p = places.get(r['place_key'])
        if p is None:
            p = places[r['place_key']] = {
                'place_key': r['place_key'], 'savers': set(), 'weight': 0.0,
                'scores': [], 'latest': r['created_at'], **{
                    k: r[k] for k in ('name', 'category', 'latitude', 'longitude', 'address')},
            }
        p['savers'].add(r['user_id'])
        p['weight'] += decay(r['created_at'], now)
        if r['potential_score'] is not None:
            p['scores'].append(r['potential_score'])
        if r['created_at'] > p['latest']:
            # Keep the freshest metadata (names/addresses get corrected over time).
            p['latest'] = r['created_at']
            for k in ('name', 'category', 'address'):
                p[k] = r[k]
    return list(places.values())


def recommend(user_rows, community_rows, lat=None, lon=None, limit=8, now=None):
    """
    Rank places the user hasn't saved yet.

    user_rows / community_rows: dicts with place_key, user_id, name, category,
    latitude, longitude, address, potential_score, created_at (aware datetime).
    community_rows should include the user's own rows; they count toward
    popularity but those places are excluded from the output.
    """
    now = now or datetime.now(timezone.utc)
    saved = {r['place_key'] for r in user_rows}
    candidates = [p for p in aggregate_community(community_rows, now) if p['place_key'] not in saved]
    if not candidates:
        return []

    affinity = category_affinity(user_rows, now)
    anchor = (lat, lon) if lat is not None and lon is not None else centroid(user_rows)
    max_log = max(math.log1p(p['weight']) for p in candidates) or 1.0

    ranked = []
    for p in candidates:
        signals = {'popularity': math.log1p(p['weight']) / max_log}
        reasons = []
        n = len(p['savers'])
        reasons.append(f'Saved by {n} {"person" if n == 1 else "people"}')

        if affinity:
            a = affinity.get(p['category'], 0.0)
            signals['affinity'] = a
            if a >= 0.5:
                reasons.append(f'You often save {p["category"].replace("_", " ")} places')
        if anchor:
            d = haversine_km(anchor[0], anchor[1], p['latitude'], p['longitude'])
            signals['proximity'] = math.exp(-d / PROXIMITY_SCALE_KM)
            p['distance_km'] = round(d, 1)
            if d <= PROXIMITY_SCALE_KM:
                reasons.append(f'{d:.1f} km from {"you" if lat is not None else "your saved places"}')
        if p['scores']:
            avg = sum(p['scores']) / len(p['scores'])
            signals['quality'] = avg / 100.0
            if avg >= 70:
                reasons.append(f'Strong location score ({avg:.0f}/100)')
        else:
            signals['quality'] = 0.5  # neutral: unknown, neither boosted nor punished

        total_w = sum(WEIGHTS[s] for s in signals)
        score = sum(WEIGHTS[s] * v for s, v in signals.items()) / total_w
        ranked.append({
            'place_key': p['place_key'], 'name': p['name'], 'category': p['category'],
            'latitude': p['latitude'], 'longitude': p['longitude'], 'address': p['address'],
            'savers': n, 'distance_km': p.get('distance_km'),
            'potential_score': round(sum(p['scores']) / len(p['scores'])) if p['scores'] else None,
            'score': round(score, 4), 'reasons': reasons,
        })

    ranked.sort(key=lambda r: (-r['score'], -r['savers'], r['name']))
    return ranked[:limit]
