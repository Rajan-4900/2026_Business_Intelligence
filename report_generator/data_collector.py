"""
Builds the analysis snapshot a report is written from.

Every number here comes from the platform's existing engines, run on the
server for the requested coordinates:

  * business_intelligence.analysis   – Overpass fetch, 9-sector heatmap,
                                       decision-tree recommendation, Go/No-Go rules
  * business_intelligence.utils      – calculate_smart_revenue (Extended Huff engine)
  * business_intelligence.prediction_engine – the engine's layers, to expose the
                                       intermediate values behind the forecast

Nothing is filled in when a source fails: the section is marked
'unavailable' with a reason and listed under snapshot['missing'].
"""
import logging
from collections import Counter
from datetime import datetime, timezone

from business_intelligence import analysis, utils
from business_intelligence.prediction_engine import (
    ExtendedHuffModel,
    FeatureExtractor,
    HuffModel,
    haversine_distance,
)
from business_intelligence.prediction_engine.config import BUSINESS_METRICS
from business_intelligence.prediction_engine.huff_layer import is_competitor

logger = logging.getLogger(__name__)

UNAVAILABLE = 'Data unavailable for this analysis.'

RING_LABELS = ['0 – 667 m', '667 – 1,333 m', '1,333 – 2,000 m']
# Wedges are cut by math angle atan2(dlat, dlon) + 180°, i.e. compass bearings:
WEDGE_LABELS = ['South-west (bearing 150°–270°)', 'East (bearing 30°–150°)', 'North-west (bearing 270°–30°)']

# Fields calculate_smart_revenue returns that its own source marks as
# "mock proxy" values. They are never shown as measurements.
PROXY_FIELDS = {
    'conversion_rate': 'derived from the competition score, not a conversion rate',
    'customer_quality': 'derived from the income proxy, not a measured customer metric',
    'dynamic_avg_spend': 'derived from the income proxy, not observed spending',
    'effective_customers': 'fixed 10% of the visitor proxy, not counted customers',
}

FOOD = {'cafe', 'restaurant', 'fast_food', 'food_court', 'bar', 'pub', 'ice_cream', 'bakery', 'biergarten'}
HEALTH = {'pharmacy', 'hospital', 'clinic', 'doctors', 'dentist', 'veterinary', 'chemist'}
EDUCATION = {'school', 'college', 'university', 'kindergarten', 'library', 'training'}
FINANCE = {'bank', 'atm', 'bureau_de_change'}
TRANSPORT_AMENITY = {'bus_station', 'parking', 'fuel', 'taxi', 'ferry_terminal', 'bicycle_parking', 'charging_station'}


class CollectionError(Exception):
    """Raised when the core map data cannot be retrieved at all."""


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _coords(el):
    lat = el.get('lat') or (el.get('center') or {}).get('lat')
    lon = el.get('lon') or (el.get('center') or {}).get('lon')
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


def _family(tags):
    """Coarse category of an OSM feature, for the distribution chart."""
    amenity = tags.get('amenity')
    if tags.get('shop'):
        return 'Shops'
    if amenity in FOOD:
        return 'Food & drink'
    if amenity in HEALTH:
        return 'Healthcare'
    if amenity in EDUCATION:
        return 'Education'
    if amenity in FINANCE:
        return 'Banks & ATMs'
    if (amenity in TRANSPORT_AMENITY or tags.get('public_transport') or tags.get('railway')
            or tags.get('highway') == 'bus_stop'):
        return 'Transport & parking'
    if tags.get('office'):
        return 'Offices'
    if tags.get('tourism'):
        return 'Tourism & hotels'
    if amenity:
        return 'Other amenities'
    if tags.get('highway'):
        return 'Roads & paths'
    if tags.get('building'):
        return 'Buildings'
    return 'Other'


def _poi_type(tags):
    return (tags.get('amenity') or tags.get('shop') or tags.get('tourism') or '').lower().replace(' ', '_')


def _summarise_pois(elements, lat, lon, radius_m):
    families = Counter()
    specific = Counter()
    points = []
    named = 0
    in_radius = 0
    for el in elements:
        tags = el.get('tags') or {}
        c = _coords(el)
        if not c:
            continue
        if haversine_distance(lat, lon, c[0], c[1]) > radius_m:
            continue
        in_radius += 1
        fam = _family(tags)
        families[fam] += 1
        t = _poi_type(tags)
        if t:
            specific[t] += 1
        if tags.get('name'):
            named += 1
        points.append((round(c[0], 6), round(c[1], 6), fam))
    return {
        'status': 'ok' if in_radius else 'unavailable',
        'reason': '' if in_radius else 'OpenStreetMap returned no mapped features with coordinates within 2 km.',
        'total_returned': len(elements),
        'in_radius': in_radius,
        'named': named,
        'by_family': families.most_common(),
        'top_types': specific.most_common(12),
        'points': points,
    }


def _heatmap(elements, lat, lon, radius_m):
    grid = analysis.classify_sectors(elements, lat, lon, radius_m)
    by_key = {}
    for level in ('high', 'medium', 'low'):
        for area in grid[level]:
            by_key[area['sector']] = (level, area)

    sectors = []
    for ring in range(3):
        for wedge in range(3):
            key = f'{ring}_{wedge}'
            level, area = by_key.pop(key, (None, None))
            sectors.append({
                'key': key,
                'ring': RING_LABELS[ring],
                'wedge': WEDGE_LABELS[wedge],
                'count': area['count'] if area else 0,
                'intensity': level or 'empty',
                'latitude': area['latitude'] if area else None,
                'longitude': area['longitude'] if area else None,
            })
    # Boundary keys (a feature exactly on the 2 km edge or due west) and the
    # no-data placeholder are kept but listed separately.
    extra = [{'key': k, 'intensity': lvl, 'count': a['count'],
              'latitude': a['latitude'], 'longitude': a['longitude']} for k, (lvl, a) in by_key.items()]

    counts = {lvl: len(grid[lvl]) for lvl in ('high', 'medium', 'low')}
    counts['empty'] = sum(1 for s in sectors if s['intensity'] == 'empty')
    return {
        'status': 'ok',
        'dominant': grid['dominant'],
        'placeholder_used': grid['placeholder_used'],
        'sectors': sectors,
        'extra_sectors': extra,
        'counts': counts,
        'areas': {lvl: grid[lvl] for lvl in ('high', 'medium', 'low')},
        'thresholds': {
            'high': f'{analysis.HIGH_SECTOR_MIN_POIS} or more mapped features',
            'medium': f'{analysis.MEDIUM_SECTOR_MIN_POIS}–{analysis.HIGH_SECTOR_MIN_POIS - 1} mapped features',
            'low': f'1–{analysis.MEDIUM_SECTOR_MIN_POIS - 1} mapped features',
        },
        # What the website's footer shows, with its real meaning.
        'website_crowd_score': utils.calculate_crowd_score(elements),
        'website_legacy_revenue': utils.predict_revenue(utils.calculate_crowd_score(elements)),
    }


def _competitors(elements, lat, lon, business_type):
    """Same matching rule as the Huff layer (is_competitor), with names kept."""
    b_key = business_type.strip().lower().replace(' ', '_')
    found = []
    for el in elements:
        tags = el.get('tags') or {}
        poi_type = _poi_type(tags)
        if not is_competitor(poi_type, b_key):
            continue
        c = _coords(el)
        if not c:
            continue
        dist = haversine_distance(lat, lon, c[0], c[1])
        if dist <= 10.0:
            continue
        found.append({
            'name': tags.get('name') or 'Unnamed (mapped without a name)',
            'type': poi_type.replace('_', ' '),
            'distance_m': round(dist),
        })
    found.sort(key=lambda r: r['distance_m'])
    distances = [r['distance_m'] for r in found]
    bins = [('0–250 m', 0, 250), ('250–500 m', 250, 500), ('500 m–1 km', 500, 1000),
            ('1–1.5 km', 1000, 1500), ('1.5–2 km', 1500, 2000), ('> 2 km', 2000, float('inf'))]
    return {
        'status': 'ok',
        'business_type': business_type,
        'match_key': b_key,
        'count': len(found),
        'within_500_m': sum(1 for d in distances if d <= 500),
        'within_1000_m': sum(1 for d in distances if d <= 1000),
        'nearest_m': distances[0] if distances else None,
        'distance_bins': [(label, sum(1 for d in distances if lo < d <= hi))
                          for label, lo, hi in bins],
        'list': found[:12],
    }


def _revenue(elements, lat, lon, business_type):
    """calculate_smart_revenue plus the engine's intermediate values."""
    result = utils.calculate_smart_revenue(elements, business_type=business_type, lat=lat, lon=lon)
    b_key = business_type.strip().lower().replace(' ', '_')
    uses_default = b_key not in BUSINESS_METRICS
    metrics = BUSINESS_METRICS.get(b_key, BUSINESS_METRICS['default'])

    monthly = float(result.get('monthly_revenue') or 0)
    rng = result.get('revenue_range') or {}
    scenarios = None
    if monthly > 0 and rng.get('min') is not None and rng.get('max') is not None:
        scenarios = {
            'conservative': float(rng['min']),
            'base': monthly,
            'optimistic': float(rng['max']),
            'spread_pct': round((float(rng['max']) / monthly - 1.0) * 100),
        }

    revenue = {
        'status': 'ok',
        'business_type': business_type,
        'engine_key': b_key,
        'uses_default_assumptions': uses_default,
        'assumptions': {
            'avg_spend': metrics['avg_spend'],
            'conversion_rate': metrics['base_conv'],
            'category_label': metrics['label'],
            'optimal_daily_customers': list(metrics['optimal_range']),
            'crowding_sensitivity': metrics['sensitivity'],
        },
        'daily': result['daily_revenue'],
        'weekly': result['weekly_revenue'],
        'monthly': result['monthly_revenue'],
        'annual': result['annual_revenue'],
        'range': {'min': rng.get('min'), 'max': rng.get('max')},
        'scenarios': scenarios,
        'potential_score': result['potential_score'],
        'confidence_score': result['confidence_score'],
        'risk_level': result['risk_level'],
        'business_health': result['business_health'],
        'positive_factors': list(result.get('top_positive_factors') or []),
        'negative_factors': list(result.get('top_negative_factors') or []),
        'engine_recommendations': list(result.get('recommendations') or []),
        'excluded_proxy_fields': PROXY_FIELDS,
        'breakdown': None,
    }

    try:
        revenue['breakdown'] = _revenue_breakdown(elements, lat, lon, business_type, b_key, metrics,
                                                  result['daily_revenue'])
    except Exception:  # breakdown is explanatory only; the forecast above stands
        logger.exception('Revenue breakdown failed')
    return revenue


def _revenue_breakdown(elements, lat, lon, business_type, b_key, metrics, engine_daily):
    """
    Re-run the engine's layers with the same inputs predict_site_revenue uses
    to expose the values it does not return. If the layers do not reproduce
    the engine's daily revenue exactly, the breakdown is discarded.
    """
    features = FeatureExtractor(lat, lon, business_type).extract_features(elements)
    huff = HuffModel(lat, lon, b_key).compute_huff_metrics(
        elements=elements,
        accessibility_score=features.accessibility_score,
        business_attraction_score=features.business_attraction_score,
        area_diversity_score=features.area_diversity_score,
        income_proxy=features.income_proxy,
        expected_visitors=features.expected_visitors,
    )
    ext = ExtendedHuffModel(b_key).compute_extended_metrics(
        elements=elements,
        market_share=huff.market_share,
        expected_visitors=features.expected_visitors,
        accessibility_score=features.accessibility_score,
        competition_score=features.competition_score,
        demand_supply_ratio=features.demand_supply_ratio,
    )
    if abs(round(ext.retail_turnover, 2) - float(engine_daily)) > 0.01:
        return None
    denom = metrics['avg_spend'] * ext.business_performance
    daily_customers = ext.retail_turnover / denom if denom else None
    return {
        'visitor_proxy': features.expected_visitors,
        'market_share': huff.market_share,
        'competition_adjustment': ext.competition_adjustment,
        'business_performance': ext.business_performance,
        'daily_customers': round(daily_customers, 1) if daily_customers is not None else None,
        'accessibility_score': features.accessibility_score,
        'attraction_score': features.business_attraction_score,
        'competition_score': features.competition_score,
        'demand_supply_ratio': features.demand_supply_ratio,
        'transit_score': features.transit_score,
        'walkability_score': features.walkability_score,
        'diversity_score': features.area_diversity_score,
        'income_proxy': features.income_proxy,
        'customer_mix': features.customer_mix,
    }


def feasibility_elements(elements):
    """Features the feasibility query would return: those with amenity, shop or tourism keys."""
    return [el for el in elements if any(k in (el.get('tags') or {}) for k in ('amenity', 'shop', 'tourism'))]


def _candidate_list(prediction, requested):
    seen = set()
    out = []

    def add(name, source):
        key = (name or '').strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append({'business': name.strip(), 'source': source})

    if requested:
        add(requested, 'Your selected business')
    if prediction:
        add(prediction['primary'], 'ML model (primary)')
        for alt in prediction.get('alternatives') or []:
            add(alt['business'], f"ML model (alternative for {alt['intensity']} intensity)")
    return out[:4]


def collect_analysis(lat, lon, name, radius_m, business_type='', progress=None):
    """
    Run the platform's analysis for one location and return the snapshot.
    `progress(stage)` is called as each real step finishes ('collect',
    'crowd', 'recommend', 'revenue'). Raises CollectionError if
    OpenStreetMap data cannot be fetched at all.
    """
    progress = progress or (lambda stage: None)
    missing = []
    sources = []
    collected_at = _now_iso()

    results, error = analysis._run_overpass_query(analysis._build_overpass_query(lat, lon, radius_m), timeout=30)
    if error or results is None:
        raise CollectionError('OpenStreetMap data could not be retrieved (Overpass API). Please try again shortly.')
    elements = results.get('elements', [])
    sources.append({
        'name': 'OpenStreetMap features via the Overpass API',
        'detail': f'amenity, shop, tourism, building, office, highway, railway and public_transport features '
                  f'within {radius_m} m; {len(elements)} features returned',
        'retrieved_at': collected_at,
        'note': 'Responses are cached by the platform for up to 15 minutes.',
    })
    progress('collect')

    snapshot = {
        'location': {'name': name, 'latitude': lat, 'longitude': lon, 'radius_m': radius_m},
        'collected_at': collected_at,
        'sources': sources,
        'missing': missing,
        'pois': _summarise_pois(elements, lat, lon, radius_m),
        'heatmap': _heatmap(elements, lat, lon, radius_m),
    }
    if snapshot['pois']['status'] != 'ok':
        missing.append({'item': 'Mapped features near the location', 'reason': snapshot['pois']['reason']})
    if snapshot['heatmap']['placeholder_used']:
        missing.append({'item': 'Sector-level crowd intensity',
                        'reason': 'No mapped features with coordinates were found, so no sector could be classified. '
                                  'The website shows a placeholder marker at the centre; it is not a measurement.'})
    progress('crowd')

    # --- ML recommendation (decision tree) ---
    try:
        prediction = analysis.build_business_prediction(snapshot['heatmap']['dominant'], elements)
        snapshot['recommendation'] = {'status': 'ok', **prediction}
    except Exception as exc:
        logger.exception('ML prediction failed')
        prediction = None
        snapshot['recommendation'] = {'status': 'unavailable', 'reason': f'The ML model could not run ({type(exc).__name__}).'}
        missing.append({'item': 'ML business recommendation', 'reason': snapshot['recommendation']['reason']})

    target = business_type or (prediction['primary'] if prediction else '')
    snapshot['target_business'] = target
    snapshot['requested_business'] = business_type
    progress('recommend')

    # --- Feasibility ---
    # /check-feasibility/ queries only amenity/shop/tourism nodes and ways
    # within 2000 m (build_feasibility_query). Those are exactly the features
    # of the main query that carry one of these keys, so filtering locally
    # gives the rules identical input without a second Overpass request.
    feas_elements = feasibility_elements(elements)
    if not target:
        snapshot['feasibility'] = {'status': 'unavailable', 'reason': 'No business type was available to test.'}
        missing.append({'item': 'Feasibility check', 'reason': snapshot['feasibility']['reason']})
    else:
        verdict = analysis.evaluate_feasibility(feas_elements, lat, lon, target)
        snapshot['feasibility'] = {'status': 'ok', 'business_type': target,
                                   'features_considered': len(feas_elements), **verdict}
        sources.append({
            'name': 'OpenStreetMap amenity/shop/tourism features (feasibility rules)',
            'detail': f'{len(feas_elements)} of the features above carry an amenity, shop or tourism tag',
            'retrieved_at': collected_at,
            'note': 'The feasibility rules count only these features, so their sector counts differ from the heatmap.',
        })

    # --- Revenue engine + competition for the target business ---
    if target:
        try:
            snapshot['revenue'] = _revenue(elements, lat, lon, target)
        except Exception as exc:
            logger.exception('Revenue engine failed')
            snapshot['revenue'] = {'status': 'unavailable', 'reason': f'The revenue engine could not run ({type(exc).__name__}).'}
            missing.append({'item': 'Revenue forecast', 'reason': snapshot['revenue']['reason']})
        snapshot['competition'] = _competitors(elements, lat, lon, target)
    else:
        reason = 'No business type was available to forecast.'
        snapshot['revenue'] = {'status': 'unavailable', 'reason': reason}
        snapshot['competition'] = {'status': 'unavailable', 'reason': reason}
        missing.append({'item': 'Revenue forecast and competitor list', 'reason': reason})

    # --- Candidate comparison (same engines, one run per candidate) ---
    candidates = []
    for cand in _candidate_list(prediction, business_type):
        row = dict(cand)
        try:
            rev = utils.calculate_smart_revenue(elements, business_type=cand['business'], lat=lat, lon=lon)
            row.update({
                'potential_score': rev['potential_score'],
                'monthly_revenue': rev['monthly_revenue'],
                'confidence_score': rev['confidence_score'],
                'risk_level': rev['risk_level'],
                'business_health': rev['business_health'],
                'uses_default_assumptions':
                    cand['business'].strip().lower().replace(' ', '_') not in BUSINESS_METRICS,
            })
        except Exception:
            logger.exception('Candidate revenue failed for %s', cand['business'])
            row['revenue_error'] = True
        row['competitors'] = _competitors(elements, lat, lon, cand['business'])['count']
        row['feasible'] = analysis.evaluate_feasibility(feas_elements, lat, lon, cand['business'])['feasible']
        candidates.append(row)
    snapshot['candidates'] = candidates
    progress('revenue')
    return snapshot
