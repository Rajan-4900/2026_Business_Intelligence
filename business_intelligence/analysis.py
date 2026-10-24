"""
Location analysis shared by the HTTP views and the PDF report generator.

Moved out of views.py unchanged (ML helpers, Overpass helpers) plus the
sector classification and feasibility rules that used to live inline in the
analyze_crowd_intensity and check_feasibility views. Keeping one copy means
the report re-derives exactly what the website shows.
"""
import math

import requests

from pathlib import Path

# Load ML model, feature columns, and per-intensity business options at module load
_MODEL_DIR = Path(__file__).resolve().parent.parent / 'crowd_heatmap_project'
_MODEL_PATH = _MODEL_DIR / 'business_model.pkl'
_DATASET_PATH = _MODEL_DIR / 'business_dataset.csv'

_model = None
_feature_columns = None
_business_choices_by_intensity = {}
# Reset on module reload to pick up retrained model
_model = None


def _load_model():
    """
    Lazy-load model, expected feature columns, and business choices per
    crowd intensity (derived from the CSV used to train the model).
    """
    global _model, _feature_columns, _business_choices_by_intensity

    if _model is None:
        import pickle
        import pandas as pd
        with open(_MODEL_PATH, 'rb') as f:
            _model = pickle.load(f)

        # Get expected columns from training data (for get_dummies alignment)
        df = pd.read_csv(_DATASET_PATH)
        X = df[['crowd', 'shops', 'area']]
        X_dummies = pd.get_dummies(X)
        _feature_columns = X_dummies.columns.tolist()

        # Build a lookup of available businesses per intensity level,
        # e.g. {"high": ["cafe", "restaurant", ...], ...}
        _business_choices_by_intensity = (
            df.groupby('crowd')['business']
            .apply(lambda s: sorted(set(s.dropna())))
            .to_dict()
        )

    return _model, _feature_columns


def get_business_choices_for_intensity(intensity: str):
    """
    Return a list of business names from the CSV for the given intensity.
    Falls back to all known businesses if the intensity key is missing.
    """
    # Ensure model/dataset are initialized so the mapping is built
    _load_model()

    normalized = (intensity or '').strip().lower()
    if not normalized:
        normalized = 'low'

    choices = _business_choices_by_intensity.get(normalized)
    if choices:
        return choices

    # Fallback: flatten all unique businesses if specific intensity not found
    all_unique = set()
    for items in _business_choices_by_intensity.values():
        all_unique.update(items)
    return sorted(all_unique)


def get_all_business_choices():
    """
    Return the entire mapping {intensity: [business, ...]} derived from
    the training CSV so the frontend can stay in sync dynamically.
    """
    _load_model()
    # Shallow copy to avoid accidental mutation from callers
    return {k: list(v) for k, v in _business_choices_by_intensity.items()}


# Intensity mapping: intensity -> list of (shops, area) variants from dataset for variety
_INTENSITY_VARIANTS = {
    'high': [('high', 'commercial'), ('high', 'market'), ('medium', 'college'), ('high', 'mall'), ('medium', 'office')],
    'medium': [('medium', 'residential'), ('medium', 'commercial'), ('low', 'residential'), ('medium', 'city_center')],
    'low': [('low', 'outskirts'), ('low', 'industrial'), ('low', 'village'), ('low', 'storage')],
}


def _infer_area_from_pois(elements):
    """Infer area type from POI tags to vary ML prediction by location."""
    type_counts = {}
    for el in (elements or []):
        tags = el.get('tags') or {}
        t = tags.get('amenity') or tags.get('shop') or tags.get('tourism') or ''
        if t:
            type_counts[t] = type_counts.get(t, 0) + 1
    if not type_counts:
        return None
    # Map POI types to dataset area values
    if type_counts.get('restaurant', 0) + type_counts.get('cafe', 0) + type_counts.get('fast_food', 0) > 3:
        return 'commercial'
    if type_counts.get('school', 0) + type_counts.get('college', 0) + type_counts.get('university', 0) > 1:
        return 'college'
    if type_counts.get('hospital', 0) + type_counts.get('pharmacy', 0) > 1:
        return 'residential'
    if type_counts.get('mall', 0) or type_counts.get('market', 0):
        return 'market' if type_counts.get('market', 0) else 'mall'
    if type_counts.get('place_of_worship', 0) + type_counts.get('community_centre', 0) > 2:
        return 'residential'
    return None


def predict_business(intensity, area_hint=None):
    """
    Predict best business type based on crowd intensity and optional area hint.
    Uses area_hint to pick a (shops, area) variant so predictions vary by location.
    """
    intensity = (intensity or 'low').strip().lower()
    variants = _INTENSITY_VARIANTS.get(intensity, _INTENSITY_VARIANTS['low'])
    # If we have an area hint, try to use a variant that matches or fall back to first
    shops, area = variants[0]
    if area_hint:
        area_lower = area_hint.strip().lower()
        for s, a in variants:
            if a == area_lower:
                shops, area = s, a
                break
    crowd = intensity
    import pandas as pd
    data = pd.DataFrame([[crowd, shops, area]], columns=['crowd', 'shops', 'area'])
    data = pd.get_dummies(data)
    model, feature_columns = _load_model()
    data = data.reindex(columns=feature_columns, fill_value=0)
    prediction = model.predict(data)
    return str(prediction[0])


# Shared Overpass helper so we can gracefully handle temporary failures /
# HTML responses and try secondary endpoints before failing.
_OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]


from django.core.cache import cache
import hashlib

def _run_overpass_query(query: str, timeout: int = 15):
    """
    Try one or more Overpass API endpoints and return parsed JSON data.
    Returns (data, error_message). On success, error_message is None.
    Uses Django's cache to prevent Overpass rate limits (Too Many Requests).
    """
    # 1. Check cache first
    query_hash = hashlib.md5(query.encode('utf-8')).hexdigest()
    cache_key = f"overpass_{query_hash}"
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data, None

    # 2. If not cached, fetch from Overpass
    last_error = None
    headers = {'User-Agent': 'CrowdHeatmapApp/1.0 (Django)'}
    for url in _OVERPASS_URLS:
        try:
            response = requests.post(
                url, data={"data": query}, headers=headers, timeout=timeout
            )
            response.raise_for_status()
            data = response.json()
            # Overpass can return error in 'remark' key
            if isinstance(data, dict) and data.get('remark'):
                last_error = data.get('remark', 'Overpass API error')
                continue
            
            # Cache the successful result for 15 minutes
            cache.set(cache_key, data, timeout=900)
            return data, None
        except requests.exceptions.Timeout:
            last_error = 'Overpass API timeout. Please try again in a moment.'
        except requests.exceptions.RequestException as exc:
            last_error = str(exc)
        except (ValueError, KeyError) as exc:
            last_error = f'Invalid Overpass response: {exc}'
            
    return None, last_error


def _build_overpass_query(lat: float, lon: float, radius: int) -> str:
    """Build an optimized Overpass query for the 20 required spatial tags."""
    return f"""[out:json][timeout:30];
(
  node["amenity"](around:{radius},{lat},{lon});
  way["amenity"](around:{radius},{lat},{lon});
  node["shop"](around:{radius},{lat},{lon});
  way["shop"](around:{radius},{lat},{lon});
  node["tourism"](around:{radius},{lat},{lon});
  way["tourism"](around:{radius},{lat},{lon});
  node["building"](around:{radius},{lat},{lon});
  way["building"](around:{radius},{lat},{lon});
  node["office"](around:{radius},{lat},{lon});
  way["office"](around:{radius},{lat},{lon});
  node["highway"](around:{radius},{lat},{lon});
  way["highway"](around:{radius},{lat},{lon});
  node["railway"](around:{radius},{lat},{lon});
  way["railway"](around:{radius},{lat},{lon});
  node["public_transport"](around:{radius},{lat},{lon});
  way["public_transport"](around:{radius},{lat},{lon});
);
out center;
"""


# ---------------------------------------------------------------------------
# Sector grid (heatmap) and feasibility rules
# ---------------------------------------------------------------------------

HEATMAP_RADIUS_M = 2000
HIGH_SECTOR_MIN_POIS = 15
MEDIUM_SECTOR_MIN_POIS = 5

_REASONING = {
    'high': 'High foot traffic in commercial area — ideal for food, retail, and services.',
    'medium': 'Moderate crowd in residential area — good for essentials like grocery, pharmacy.',
    'low': 'Low traffic in outskirts — suited for storage, warehouse, or niche ventures.',
}

_BEST_TIMES = {
    'high': 'Peak hours 10am–8pm. Morning (6–10am) has lower competition.',
    'medium': 'Steady flow 9am–7pm. Evening slightly busier.',
    'low': 'Flexible timing. Consider proximity to transport for visibility.',
}


def _group_into_sectors(elements, lat, lon, radius_m, with_details=False):
    """
    Bucket POIs into 9 sectors: 3 distance rings of radius/3 metres times
    3 compass wedges of 120°. Key is "<ring>_<wedge>". POIs outside the
    radius (or without coordinates) are dropped.
    """
    sector_size = radius_m / 3
    sectors = {}
    for element in elements:
        elem_lat = element.get('lat') or (element.get('center', {}).get('lat'))
        elem_lon = element.get('lon') or (element.get('center', {}).get('lon'))
        if not elem_lat or not elem_lon:
            continue

        # Calculate distance from center
        R = 6371000  # Earth radius in meters
        lat1_rad = math.radians(lat)
        lat2_rad = math.radians(elem_lat)
        delta_lat = math.radians(elem_lat - lat)
        delta_lon = math.radians(elem_lon - lon)

        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        distance = R * c

        if distance > radius_m:
            continue

        # Sector based on angle and distance
        angle = math.atan2(elem_lat - lat, elem_lon - lon)
        angle_deg = math.degrees(angle) + 180  # 0-360
        angle_sector = int(angle_deg / 120)  # 0-2
        dist_sector = int(distance / sector_size)  # 0-2
        sector_key = f"{dist_sector}_{angle_sector}"

        if sector_key not in sectors:
            sectors[sector_key] = []
        poi = {'lat': elem_lat, 'lon': elem_lon}
        if with_details:
            tags = element.get('tags', {})
            poi['name'] = tags.get('name', 'Unknown')
            poi['type'] = tags.get('amenity') or tags.get('shop') or tags.get('tourism', 'Unknown')
        sectors[sector_key].append(poi)
    return sectors


def _intensity_for_count(count):
    if count >= HIGH_SECTOR_MIN_POIS:
        return 'high'
    if count >= MEDIUM_SECTOR_MIN_POIS:
        return 'medium'
    return 'low'


def classify_sectors(elements, lat, lon, radius_m=HEATMAP_RADIUS_M):
    """
    Heatmap classification used by /analyze-crowd-intensity/.

    Returns a dict with the three area lists in the endpoint's response shape,
    the dominant intensity, and `placeholder_used` — True when no POI had
    coordinates and a single synthetic "high" area was put at the centre
    (the map still needs something to draw; it is not a measurement).
    """
    sectors = _group_into_sectors(elements, lat, lon, radius_m, with_details=True)

    areas = {'high': [], 'medium': [], 'low': []}
    for sector_key, pois in sectors.items():
        count = len(pois)
        # Calculate center of sector
        avg_lat = sum(p['lat'] for p in pois) / count
        avg_lon = sum(p['lon'] for p in pois) / count
        areas[_intensity_for_count(count)].append({
            'latitude': avg_lat,
            'longitude': avg_lon,
            'count': count,
            'sector': sector_key
        })

    placeholder_used = False
    # If no sectors found, create default areas based on distance
    if not areas['high'] and not areas['medium'] and not areas['low']:
        areas['high'] = [{'latitude': lat, 'longitude': lon, 'count': len(elements), 'sector': 'center'}]
        placeholder_used = True

    dominant = 'low'
    if areas['high']:
        dominant = 'high'
    elif areas['medium']:
        dominant = 'medium'

    return {
        'high': areas['high'],
        'medium': areas['medium'],
        'low': areas['low'],
        'dominant': dominant,
        'placeholder_used': placeholder_used,
    }


def build_business_prediction(dominant, elements):
    """ML business prediction block returned by /analyze-crowd-intensity/."""
    area_hint = _infer_area_from_pois(elements)
    primary = predict_business(dominant, area_hint=area_hint)
    # Business options sourced directly from the CSV
    csv_choices = get_business_choices_for_intensity(dominant)
    alternatives = []
    for alt_level in ['high', 'medium', 'low']:
        if alt_level != dominant:
            alt_biz = predict_business(alt_level)
            if alt_biz and alt_biz != primary and alt_biz not in [a['business'] for a in alternatives]:
                alternatives.append({'business': alt_biz, 'intensity': alt_level})

    return {
        'primary': primary,
        'reasoning': _REASONING.get(dominant, ''),
        'alternatives': alternatives[:2],
        'best_times': _BEST_TIMES.get(dominant, ''),
        'choices': csv_choices,
        'intensity': dominant,
        'area_hint': area_hint,
    }


def build_feasibility_query(lat, lon):
    """The feasibility check only looks at amenity/shop/tourism POIs."""
    return f"""
        [out:json][timeout:15];
        (
          node["amenity"](around:2000,{lat},{lon});
          way["amenity"](around:2000,{lat},{lon});
          node["shop"](around:2000,{lat},{lon});
          way["shop"](around:2000,{lat},{lon});
          node["tourism"](around:2000,{lat},{lon});
          way["tourism"](around:2000,{lat},{lon});
        );
        out center;
        """


_FEASIBILITY_SYNONYMS = {
    'grocery_shop': 'supermarket',
    'grocery': 'supermarket',
    'medical_store': 'pharmacy',
    'chemist': 'pharmacy',
    'pub': 'restaurant',
    'bar': 'restaurant',
    'coffee_shop': 'cafe',
    'book_shop': 'book_store',
    'cloth_store': 'clothing_store',
    'garments': 'clothing_store',
}


def evaluate_feasibility(elements, lat, lon, business_type):
    """
    Go/No-Go rules used by /check-feasibility/. Returns the endpoint's fields
    plus the evidence behind the decision (which rules fired, sector counts).
    """
    sectors = _group_into_sectors(elements, lat, lon, 2000)
    # --- DYNAMIC FEASIBILITY CORRECTION ---
    # 1. Prepare candidate types (synonyms + normalization)
    biz_normalized = business_type.lower().replace(' ', '_').strip()
    if biz_normalized.endswith('_business'):
        biz_normalized = biz_normalized[:-9]
    search_target = _FEASIBILITY_SYNONYMS.get(biz_normalized, biz_normalized)

    # 2. Check actual POI frequency in the area to provide "Dynamic Evidence"
    # If the area already has many of these businesses, it's proven to be a feasible location.
    found_count = 0
    for element in elements:
        tags = element.get('tags', {})
        # Check amenity, shop, or name for the business type
        poi_type = (tags.get('amenity') or tags.get('shop') or tags.get('tourism') or '').lower()
        poi_name = tags.get('name', '').lower()
        if biz_normalized in poi_type or search_target in poi_type or biz_normalized in poi_name:
            found_count += 1

    high_c, medium_c, low_c = 0, 0, 0
    for pois in sectors.values():
        level = _intensity_for_count(len(pois))
        if level == 'high':
            high_c += 1
        elif level == 'medium':
            medium_c += 1
        else:
            low_c += 1

    dominant = 'low'
    if high_c > 0:
        dominant = 'high'
    elif medium_c > 0:
        dominant = 'medium'

    allowed_businesses = [b.lower().replace(' ', '_') for b in get_business_choices_for_intensity(dominant)]
    recommended_primary = predict_business(dominant, _infer_area_from_pois(elements)).lower().replace(' ', '_')

    evidence = {
        'similar_businesses_found': found_count,
        'in_dataset_for_intensity': False,
        'matches_ml_recommendation': False,
        'local_proof': False,
        'high_intensity_retail_rule': False,
        'sector_counts': {'high': high_c, 'medium': medium_c, 'low': low_c},
        'allowed_businesses': allowed_businesses,
    }

    if business_type:
        # 3. Final Feasibility Decision (Permissive)
        # Feasible if:
        # - Matches CSV intensity list
        # - Matches ML primary recommendation
        # - Many similar businesses already exist in the area (dynamic proof)
        # - High intensity areas are generally feasible for most services
        is_in_dataset = (biz_normalized in allowed_businesses or search_target in allowed_businesses)
        is_recommended = (biz_normalized == recommended_primary or search_target == recommended_primary)
        has_local_proof = (found_count >= 2)  # If at least 2 exist, it's definitely feasible

        feasible = is_in_dataset or is_recommended or has_local_proof
        evidence.update({
            'in_dataset_for_intensity': is_in_dataset,
            'matches_ml_recommendation': is_recommended,
            'local_proof': has_local_proof,
        })

        # Bonus: High intensity is feasible for almost anything retail/food
        if not feasible and dominant == 'high' and ('shop' in biz_normalized or 'store' in biz_normalized or 'food' in biz_normalized):
            feasible = True
            evidence['high_intensity_retail_rule'] = True

        if feasible:
            if has_local_proof:
                message = f'✅ Feasible: We found {found_count} similar businesses in the area, confirming this is a strong location for a "{business_type}".'
            else:
                message = f'✅ Feasible: A "{business_type}" matches the {dominant} crowd profile and development level of this area.'
        else:
            message = f'❌ Not feasible: The area currently has {dominant} intensity and low indicators for "{business_type}". Consider a {recommended_primary.replace("_", " ")} instead.'
    else:
        feasible = True
        message = f'Location analyzed. Dominant crowd intensity is {dominant}. We recommend starting a {recommended_primary.replace("_", " ")} here.'

    return {
        'feasible': feasible,
        'dominant_intensity': dominant,
        'message': message,
        'recommended_business': recommended_primary,
        'evidence': evidence,
    }
