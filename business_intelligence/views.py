from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.urls import reverse
from django.contrib.auth.decorators import login_required  # kept for compatibility
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib import messages
import json
import math
import requests
from .forms import BusinessUserForm
from .models import BusinessUser
from .consumers import get_bot_response
from . import utils
from .analysis import (  # noqa: F401  (re-exported for existing importers)
    _load_model,
    get_business_choices_for_intensity,
    get_all_business_choices,
    _INTENSITY_VARIANTS,
    _infer_area_from_pois,
    predict_business,
    _OVERPASS_URLS,
    _run_overpass_query,
    _build_overpass_query,
    classify_sectors,
    build_business_prediction,
    build_feasibility_query,
    evaluate_feasibility,
    generate_location_business_recommendations,
    generate_fallback_spatial_pois,
)


def home(request):
    """Main page with map and controls."""
    return render(request, 'heatmap_app/home.html')




def dashboard(request):
    """Dashboard analytics view."""
    return render(request, 'heatmap_app/dashboard.html')


def login_view(request):
    """
    Renders the Supabase-powered authentication page with Sign In & Sign Up.
    """
    next_url = request.GET.get('next', reverse('dashboard'))
    return render(request, 'heatmap_app/login.html', {
        'next_url': next_url,
    })


def profile_view(request):
    """
    Renders the user profile management page.
    Allows editing full name, login password, avatar, and other profile details.
    """
    return render(request, 'heatmap_app/profile.html')


@csrf_exempt
@require_http_methods(['POST'])
def log_activity_api(request):
    """
    Receives frontend activity events and logs them to the Supabase project DB.
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    event_type = data.get('event_type')
    if not event_type:
        return JsonResponse({'success': False, 'message': 'event_type is required'}, status=400)

    feature_name = data.get('feature_name', '')
    user_id = data.get('user_id')
    user_email = data.get('user_email')
    details = data.get('details', {})

    # Extract client IP
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip_address = x_forwarded_for.split(',')[0].strip()
    else:
        ip_address = request.META.get('REMOTE_ADDR')

    from .supabase_service import log_activity_to_supabase
    result = log_activity_to_supabase(
        event_type=event_type,
        feature_name=feature_name,
        user_id=user_id,
        user_email=user_email,
        details=details,
        ip_address=ip_address
    )
    return JsonResponse(result)


@csrf_exempt
@require_http_methods(['POST'])
def report_user_location(request):
    """
    Receive user's current location (from browser geolocation or IP fallback).
    POST body: { "latitude": float, "longitude": float, "accuracy": int (optional), "source": "gps"|"ip" (optional) }
    Returns JSON: { "success": bool, "message": str }. Coordinates can be used for map/heatmap server-side if needed.
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)
    lat = data.get('latitude')
    lon = data.get('longitude')
    if lat is None or lon is None:
        return JsonResponse({'success': False, 'message': 'latitude and longitude are required'}, status=400)
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'message': 'latitude and longitude must be numbers'}, status=400)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return JsonResponse({'success': False, 'message': 'latitude/longitude out of range'}, status=400)
    source = data.get('source') or 'gps'
    accuracy = data.get('accuracy')
    # Optional: store in session for server-side use, e.g. request.session['user_lat'], request.session['user_lon']
    request.session['user_lat'] = lat
    request.session['user_lon'] = lon
    request.session['user_location_source'] = source
    return JsonResponse({
        'success': True,
        'message': 'Location received',
        'latitude': lat,
        'longitude': lon,
        'source': source,
    })


@csrf_exempt
@require_http_methods(['POST'])
def chat_message(request):
    """HTTP fallback for chatbot when WebSocket is not available."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'})
    user_message = (data.get('message') or '').strip()
    client_location = data.get('location')
    if not user_message:
        return JsonResponse({'success': False, 'message': 'Message is required'})
    from tracker.ai.orchestrator import process_user_query
    result = process_user_query(user_message, client_location_context=client_location)
    return JsonResponse({
        'success': result.get('success', True),
        'message': result.get('message', ''),
        'structured_actions': result.get('structured_actions', []),
        'location_context': result.get('location_context'),
        'providers_used': result.get('providers_used', [])
    })

def submit_form(request):
    """Handle form submission — validate fields and return success without DB."""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        business_type = request.POST.get('business_type', '').strip()
        crowd_intensity = request.POST.get('crowd_intensity', '').strip()

        errors = []
        if not name:
            errors.append('Name is required.')
        if not email or '@' not in email:
            errors.append('A valid email is required.')
        if not phone:
            errors.append('Phone is required.')
        if not business_type:
            errors.append('Business type is required.')
        if crowd_intensity not in ('high', 'medium', 'low'):
            errors.append('Please select a crowd intensity.')

        if errors:
            return JsonResponse({'success': False, 'message': ' | '.join(errors)})

        return JsonResponse({
            'success': True,
            'message': f'Thank you, {name}! Your business inquiry has been received.',
        })

    return JsonResponse({'success': False, 'message': 'Invalid request method'})

@csrf_exempt
def search_location(request):
    """Search for locations using Nominatim API (OpenStreetMap)"""
    if request.method == 'POST':
        data = json.loads(request.body)
        query = data.get('query', '')
        
        # Call Nominatim API for location search (India-only)
        try:
            url = "https://nominatim.openstreetmap.org/search"
            headers = {'User-Agent': 'CrowdHeatmapApp/1.0'}
            params = {
                "q": query,
                "format": "json",
                "limit": 5,
                "addressdetails": 1,
                "countrycodes": "in",
                # India bounding box: left,top,right,bottom
                "viewbox": "68,37.5,97.5,6.5",
                "bounded": 1,
            }
            response = requests.get(url, headers=headers, params=params)
            results = response.json()
            return JsonResponse({'success': True, 'results': results})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})


@csrf_exempt
def autocomplete_location(request):
    """Return lightweight suggestions for location autocomplete."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'Invalid JSON'})

        query = (data.get('query') or '').strip()
        if not query:
            return JsonResponse({'success': True, 'results': []})

        try:
            url = "https://nominatim.openstreetmap.org/search"
            headers = {'User-Agent': 'CrowdHeatmapApp/1.0'}
            params = {
                "q": query,
                "format": "json",
                "limit": 5,
                "addressdetails": 1,
                "countrycodes": "in",
                # India bounding box: left,top,right,bottom
                "viewbox": "68,37.5,97.5,6.5",
                "bounded": 1,
            }
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            raw_results = response.json()

            suggestions = []
            for r in raw_results:
                suggestions.append({
                    "display_name": r.get("display_name"),
                    "lat": r.get("lat"),
                    "lon": r.get("lon"),
                })

            return JsonResponse({'success': True, 'results': suggestions})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'message': 'Invalid request method'})

def _haversine_distance_m(lat1, lon1, lat2, lon2):
    r = 6371000.0  # Earth's radius in meters
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def get_location_recommendations(request):
    """
    Return top 5 ranked location-specific business recommendations
    based on the 5km trading zone around lat, lon.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    else:
        data = request.GET

    lat = data.get('latitude') or data.get('lat')
    lon = data.get('longitude') or data.get('lon') or data.get('lng')
    location_name = data.get('location_name') or data.get('name') or 'Selected Location'
    radius = int(data.get('radius') or 5000)

    if lat is None or lon is None:
        return JsonResponse({'success': False, 'error': 'Latitude and longitude are required'}, status=400)

    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Invalid coordinates'}, status=400)

    recs = generate_location_business_recommendations(lat, lon, radius_m=radius, location_name=location_name)
    return JsonResponse({
        'success': True,
        'analysis_radius': radius,
        'location': {
            'name': location_name,
            'latitude': lat,
            'longitude': lon,
            'radius': radius
        },
        'recommendations': recs,
        'count': len(recs)
    })


@csrf_exempt
@require_http_methods(['POST'])
def find_popular_places(request):
    """Find popular places within an exact 5km radius using optimized Overpass spatial query."""
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    lat = data.get('latitude')
    lon = data.get('longitude')
    loc_name = data.get('name') or data.get('location_name') or 'Selected Location'
    if lat is None or lon is None:
        return JsonResponse({
            'success': False,
            'error': 'Latitude and longitude are required'
        }, status=400)
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Invalid coordinates'}, status=400)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return JsonResponse({'success': False, 'error': 'Coordinates out of range'}, status=400)

    # 5 km radius analysis query
    analysis_radius = 5000
    query = _build_overpass_query(lat, lon, analysis_radius)
    results, error = _run_overpass_query(query, timeout=5, lat=lat, lon=lon, radius=analysis_radius)
    if error or results is None:
        return JsonResponse({
            'success': False,
            'error': error or 'Unable to fetch popular places. Please try again.'
        })
    raw_elements = results.get('elements', [])
    
    # Strict 5 km Haversine boundary filter (points <= 5000m included, > 5000m excluded)
    elements = []
    for el in raw_elements:
        e_lat = el.get('lat') or (el.get('center') or {}).get('lat')
        e_lon = el.get('lon') or (el.get('center') or {}).get('lon')
        if e_lat is not None and e_lon is not None:
            dist = _haversine_distance_m(lat, lon, float(e_lat), float(e_lon))
            if dist <= float(analysis_radius):
                el_copy = dict(el)
                el_copy['distance_m'] = round(dist, 1)
                elements.append(el_copy)
        else:
            elements.append(el)

    # --- PER-PLACE REVENUE CALCULATION ---
    enriched_places, total_area_revenue = utils.enrich_places_with_revenue(elements)
    
    # --- UNIFIED CROWD INTENSITY CALCULATION (Avoids 2nd redundant network call) ---
    grid = classify_sectors(elements, lat, lon, radius_m=analysis_radius)
    crowd_score = utils.calculate_crowd_score(elements)
    est_revenue = utils.predict_revenue(crowd_score)
    
    business_prediction = None
    try:
        business_prediction = build_business_prediction(grid['dominant'], elements)
        business_prediction.pop('area_hint', None)
    except Exception:
        pass

    crowd_intensity_data = {
        'success': True,
        'high_intensity': grid['high'],
        'medium_intensity': grid['medium'],
        'low_intensity': grid['low'],
        'dominant': grid['dominant'],
        'total_pois': len(elements),
        'crowd_score': crowd_score,
        'estimated_revenue': est_revenue,
        'business_prediction': business_prediction,
        'business_by_intensity': get_all_business_choices(),
        'analysis_radius': analysis_radius,
    }

    # Generate 5 dynamic location-specific business recommendations
    recs = generate_location_business_recommendations(lat, lon, radius_m=analysis_radius, location_name=loc_name, elements=elements)

    is_live = results.get('is_live', True)
    data_source = results.get('data_source', 'Verified live OpenStreetMap' if is_live else 'Estimated crowd density based on available signals')

    return JsonResponse({
        'success': True, 
        'results': enriched_places,
        'places': enriched_places,
        'total_area_revenue': total_area_revenue if total_area_revenue > 0 else est_revenue,
        'estimated_revenue': total_area_revenue if total_area_revenue > 0 else est_revenue,
        'active_sensors_count': len(elements),
        'active_sensors': len(elements),
        'analysis_radius': analysis_radius,
        'crowd_intensity': crowd_intensity_data,
        'recommendations': recs,
        'is_live': is_live,
        'data_source': data_source,
        'data_quality': results.get('data_quality', 'Verified live' if is_live else 'Signal-based estimate'),
    })

@csrf_exempt
@csrf_exempt
def analyze_crowd_intensity(request):
    """Analyze crowd intensity in exact 5km radius and return high/medium/low areas."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

        lat = data.get('latitude')
        lon = data.get('longitude')
        
        if not lat or not lon:
            return JsonResponse({'success': False, 'message': 'Latitude and longitude are required'})
        
        try:
            lat = float(lat)
            lon = float(lon)
            analysis_radius = 5000
            
            # Use Overpass API to find amenities and POIs within 5km radius
            query = _build_overpass_query(lat, lon, analysis_radius)
            results, error = _run_overpass_query(query, timeout=20, lat=lat, lon=lon, radius=analysis_radius)
            if error or results is None:
                return JsonResponse({'success': False, 'error': error or 'Unable to analyze crowd intensity'})

            raw_elements = results.get('elements', [])
            elements = []
            for el in raw_elements:
                e_lat = el.get('lat') or (el.get('center') or {}).get('lat')
                e_lon = el.get('lon') or (el.get('center') or {}).get('lon')
                if e_lat is not None and e_lon is not None:
                    if _haversine_distance_m(lat, lon, float(e_lat), float(e_lon)) <= float(analysis_radius):
                        elements.append(el)
                else:
                    elements.append(el)

            # 9 sectors (3 rings x 3 wedges within 5km)
            grid = classify_sectors(elements, lat, lon, radius_m=analysis_radius)
            high_intensity_areas = grid['high']
            medium_intensity_areas = grid['medium']
            low_intensity_areas = grid['low']

            # ML business prediction based on dominant intensity (location-aware)
            business_prediction = None
            try:
                business_prediction = build_business_prediction(grid['dominant'], elements)
                business_prediction.pop('area_hint', None)
            except Exception:
                pass  # Heatmap still works; frontend handles null

            crowd_score = utils.calculate_crowd_score(elements)
            estimated_rev = utils.predict_revenue(crowd_score)

            is_live = results.get('is_live', True)
            data_source = results.get('data_source', 'Verified live OpenStreetMap' if is_live else 'Estimated crowd density based on available signals')

            return JsonResponse({
                'success': True,
                'high_intensity': high_intensity_areas,
                'medium_intensity': medium_intensity_areas,
                'low_intensity': low_intensity_areas,
                'total_pois': len(elements),
                'active_sensors_count': len(elements),
                'analysis_radius': analysis_radius,
                'business_prediction': business_prediction,
                'business_by_intensity': get_all_business_choices(),
                'crowd_score': crowd_score,
                'estimated_revenue': estimated_rev,
                'is_live': is_live,
                'data_source': data_source,
                'data_quality': results.get('data_quality', 'Verified live' if is_live else 'Signal-based estimate'),
            })
            
        except Exception as e:
            import traceback
            return JsonResponse({'success': False, 'error': str(e), 'traceback': traceback.format_exc()})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})


@csrf_exempt
def check_feasibility(request):
    """
    Check if a business type is feasible at the given location based on crowd intensity.
    POST: { latitude, longitude, business_type (optional) }
    Returns: { success, feasible, dominant_intensity, message, latitude, longitude }
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method'})
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'})
    lat = data.get('latitude')
    lon = data.get('longitude')
    business_type = (data.get('business_type') or '').strip()
    if not lat or not lon:
        return JsonResponse({'success': False, 'message': 'Latitude and longitude are required'})
    try:
        results, error = _run_overpass_query(build_feasibility_query(lat, lon), timeout=15)
        if error or results is None:
            return JsonResponse({'success': False, 'error': error or 'Unable to analyze location'})
        elements = results.get('elements', [])
        verdict = evaluate_feasibility(elements, lat, lon, business_type)
        feasible = verdict['feasible']
        dominant = verdict['dominant_intensity']
        message = verdict['message']
        recommended_primary = verdict['recommended_business']
        return JsonResponse({
            'success': True,
            'feasible': feasible,
            'dominant_intensity': dominant,
            'message': message,
            'latitude': lat,
            'longitude': lon,
            'recommended_business': recommended_primary,
        })
    except Exception as e:
        import traceback
        return JsonResponse({'success': False, 'error': str(e), 'traceback': traceback.format_exc()})
def business_recommendations(request):
    # Keep legacy route but serve the dashboard AI flow directly so the
    # sidebar button always opens live recommendation data.
    return redirect(f"{reverse('dashboard')}?ai=true")


def _extract_coordinates(payload):
    lat = payload.get('latitude')
    lon = payload.get('longitude')
    if lat is None and payload.get('lat') is not None:
        lat = payload.get('lat')
    if lon is None and payload.get('lng') is not None:
        lon = payload.get('lng')
    if lat is None or lon is None:
        raise ValueError('Latitude and longitude are required')
    lat = float(lat)
    lon = float(lon)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('Coordinates out of range')
    return lat, lon


@csrf_exempt
@require_http_methods(['POST'])
def analyze_location(request):
    """
    Analyze a selected location and return:
    - smart revenue forecast
    - strategic recommendations
    - crowd score and feasibility score
    """
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    try:
        lat, lon = _extract_coordinates(data)
    except (ValueError, TypeError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    business_type = (data.get('business_type') or data.get('type') or 'default').strip()

    query = _build_overpass_query(lat, lon, 2000)
    results, error = _run_overpass_query(query, timeout=30)
    if error or results is None:
        return JsonResponse({'success': False, 'error': error or 'Unable to analyze location'}, status=502)

    elements = results.get('elements', [])
    revenue_data = utils.calculate_smart_revenue(elements, business_type=business_type, lat=lat, lon=lon)
    crowd_score = utils.calculate_crowd_score(elements)

    # Recommended business from location dynamics when caller did not pass specific type.
    area_hint = _infer_area_from_pois(elements)
    if crowd_score >= 70:
        dominant = 'high'
    elif crowd_score >= 35:
        dominant = 'medium'
    else:
        dominant = 'low'
    recommended_business = predict_business(dominant, area_hint=area_hint)

    return JsonResponse({
        'success': True,
        'latitude': lat,
        'longitude': lon,
        'business_type': business_type,
        'revenue_data': revenue_data,
        'recommendations': revenue_data.get('recommendations', []),
        'crowd_score': crowd_score,
        'feasibility_score': revenue_data.get('potential_score', 0),
        'potential_score': revenue_data.get('potential_score', 0),
        'recommended_business': recommended_business,
    })


@csrf_exempt
@require_http_methods(['POST'])
def generate_best_locations(request):
    """
    Generate 1-3 best business locations (ML-style feasibility) around a base point.
    """
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    try:
        if data.get('latitude') is None or data.get('longitude') is None:
            # Fallback chain: session -> India center default.
            lat = request.session.get('user_lat', 19.0760)
            lon = request.session.get('user_lon', 72.8777)
        else:
            lat, lon = _extract_coordinates(data)
    except (ValueError, TypeError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    query = _build_overpass_query(lat, lon, 8000)
    results, error = _run_overpass_query(query, timeout=30)
    if error or results is None:
        return JsonResponse({'success': False, 'error': error or 'Unable to generate locations'}, status=502)

    elements = results.get('elements', [])
    top = utils.generate_best_location_candidates(lat, lon, elements, top_n=3)

    return JsonResponse({
        'success': True,
        'base_location': {'lat': lat, 'lng': lon},
        'locations': top,
    })

@require_http_methods(['GET'])
def get_business_types(request):
    """Return all dynamic expected business choices for the form dropdown."""
    lat = request.GET.get('lat')
    lon = request.GET.get('lon')
    
    # Can optimize by returning all unique business choices
    choices_by_intensity = get_all_business_choices()
    all_choices = set()
    for intensity, choices in choices_by_intensity.items():
        all_choices.update(choices)
    
    # Format for the frontend
    business_types = [{'value': c, 'label': c.replace('_', ' ').title()} for c in sorted(all_choices)]
    return JsonResponse({'success': True, 'business_types': business_types})

@csrf_exempt
@require_http_methods(['POST'])
def find_matching_locations(request):
    """
    Find 1-3 locations in a 5km radius that satisfy the exact crowd intensity and business category.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'})
        
    lat = data.get('latitude')
    lon = data.get('longitude')
    business_type = (data.get('business_type') or '').strip().lower()
    crowd_intensity = (data.get('crowd_intensity') or '').strip().lower()
    
    if not lat or not lon:
        return JsonResponse({'success': False, 'message': 'Latitude and longitude are required'})
        
    try:
        lat = float(lat)
        lon = float(lon)
        
        # 1. Get POIs in 5km radius
        query = _build_overpass_query(lat, lon, 5000)
        results, error = _run_overpass_query(query, timeout=30)
        if error or results is None:
            return JsonResponse({'success': False, 'error': error or 'Unable to analyze location'})
            
        elements = results.get('elements', [])
        
        # 2. Divide area into sectors and calculate intensity
        sector_size = 5000 / 3
        sectors = {}
        
        for element in elements:
            elem_lat = element.get('lat') or (element.get('center', {}).get('lat'))
            elem_lon = element.get('lon') or (element.get('center', {}).get('lon'))
            if not elem_lat or not elem_lon: continue
            
            # Distance from center
            R = 6371000
            lat1_rad = math.radians(lat)
            lat2_rad = math.radians(elem_lat)
            delta_lat = math.radians(elem_lat - lat)
            delta_lon = math.radians(elem_lon - lon)
            a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            distance = R * c
            
            if distance > 5000: continue
            
            angle = math.atan2(elem_lat - lat, elem_lon - lon)
            angle_deg = math.degrees(angle) + 180
            angle_sector = int(angle_deg / 120)
            dist_sector = int(distance / sector_size)
            sector_key = f"{dist_sector}_{angle_sector}"
            
            if sector_key not in sectors: sectors[sector_key] = []
            sectors[sector_key].append({'lat': elem_lat, 'lon': elem_lon})

        matching_locations = []
        
        # 3. Find sectors matching the requested crowd intensity
        for sector_key, pois in sectors.items():
            count = len(pois)
            if count >= 15:
                sector_intensity = 'high'
            elif count >= 5:
                sector_intensity = 'medium'
            else:
                sector_intensity = 'low'
                
            # If the user's requested crowd intensity matches this sector's intensity
            if sector_intensity == crowd_intensity:
                # Check business feasibility in this sector
                # (For simplicity, if intensity matches, we consider it feasible,
                # as business types mapped to intensities are generally feasible there)
                
                avg_lat = sum(p['lat'] for p in pois) / count
                avg_lon = sum(p['lon'] for p in pois) / count
                
                matching_locations.append({
                    'lat': avg_lat,
                    'lon': avg_lon,
                    'intensity': sector_intensity,
                    'business': business_type
                })
                
                if len(matching_locations) >= 3:
                    break

        # 4. If no exact match, fallback to the requested base point (for UX)
        if not matching_locations:
            matching_locations.append({'lat': lat, 'lon': lon, 'intensity': crowd_intensity, 'business': business_type})
            
        return JsonResponse({
            'success': True,
            'matches': matching_locations
        })
        
    except Exception as e:
        import traceback
        return JsonResponse({'success': False, 'error': str(e), 'traceback': traceback.format_exc()})
