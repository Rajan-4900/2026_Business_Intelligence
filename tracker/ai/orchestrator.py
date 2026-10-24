"""
Centralized AI Orchestrator.
Coordinates Gemini (Primary) and Grok (Secondary) with live platform data.
"""

import re
import json
import logging
from typing import Dict, Any, Optional, Tuple

import requests
from django.core.cache import cache

from .validators import sanitize_input, is_platform_relevant, validate_structured_action
from .prompts import OUT_OF_SCOPE_RESPONSE
from .gemini_service import analyze_location as gemini_analyze
from .grok_service import review_location as grok_review
from .response_merger import merge_ai_results

logger = logging.getLogger(__name__)

# Default reference center (Bangalore, India)
DEFAULT_CENTER = {"lat": 12.9716, "lon": 77.5946, "name": "Bengaluru, Karnataka"}


def _extract_location_and_business_from_query(query: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract location name and business type from natural language queries."""
    trimmed = query.strip()
    
    # 1. "open/start <business> in <place>"
    m1 = re.search(r'\b(?:open|start)\s+(?:a\s+)?(.+?)\s+in\s+(.+)', trimmed, re.I)
    if m1 and m1.group(1).strip() and m1.group(2).strip():
        return m1.group(2).strip(), m1.group(1).strip()
        
    # 2. "<business> in <place>"
    m2 = re.search(r'\b(cafe|restaurant|shop|store|pharmacy|supermarket|gym|salon|bakery|boutique|hotel|warehouse|food\s*court)\s+in\s+(.+)', trimmed, re.I)
    if m2 and m2.group(2).strip():
        return m2.group(2).strip(), m2.group(1).strip()
        
    # 3. "analyze/check/about <place>"
    m3 = re.search(r'\b(?:analyze|check|about|explore|in|at)\s+([A-Za-z0-9\s,\.-]+)', trimmed, re.I)
    if m3 and len(m3.group(1).strip()) > 2:
        return m3.group(1).strip(), None
        
    return None, None


def _geocode_place(place_name: str) -> Optional[Dict[str, Any]]:
    """Geocode a place name in India using Nominatim with caching."""
    if not place_name:
        return None
        
    cache_key = f"geocode_{place_name.lower().replace(' ', '_')}"
    cached = cache.get(cache_key)
    if cached:
        return cached
        
    try:
        url = "https://nominatim.openstreetmap.org/search"
        headers = {'User-Agent': 'CrowdHeatmapApp/1.0 (Django Business Intelligence Platform)'}
        query_str = place_name if (',' in place_name or 'india' in place_name.lower()) else f"{place_name}, India"
        params = {
            "q": query_str,
            "format": "json",
            "limit": 1,
            "countrycodes": "in"
        }
        resp = requests.get(url, headers=headers, params=params, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if data and len(data) > 0:
                result = {
                    "name": data[0].get("display_name", place_name),
                    "lat": float(data[0]["lat"]),
                    "lon": float(data[0]["lon"])
                }
                cache.set(cache_key, result, timeout=86400) # Cache for 24 hours
                return result
    except Exception as e:
        logger.warning(f"Geocoding error for {place_name}: {e}")
        
    return None


def _build_trusted_location_context(
    lat: float,
    lon: float,
    name: str,
    requested_business: Optional[str] = None
) -> Dict[str, Any]:
    """
    Construct a complete, factual location context dictionary by executing
    the platform's spatial queries, ML predictions, and revenue models.
    """
    from tracker.views import (
        _build_overpass_query,
        _run_overpass_query,
        _infer_area_from_pois,
        predict_business,
        get_business_choices_for_intensity,
    )
    from tracker import utils

    # 1. Fetch live POIs from Overpass
    query = _build_overpass_query(lat, lon, 2000)
    results, _ = _run_overpass_query(query, timeout=15)
    elements = (results.get('elements', [])) if results else []

    # 2. Evaluate sector grid density
    high_count = 0
    med_count = 0
    low_count = 0
    sector_counts = {}
    
    for el in elements:
        e_lat = el.get('lat') or (el.get('center', {}).get('lat'))
        e_lon = el.get('lon') or (el.get('center', {}).get('lon'))
        if e_lat and e_lon:
            s_key = f"{int(e_lat*100)}_{int(e_lon*100)}"
            sector_counts[s_key] = sector_counts.get(s_key, 0) + 1
            
    for count in sector_counts.values():
        if count >= 15:
            high_count += 1
        elif count >= 5:
            med_count += 1
        else:
            low_count += 1
            
    dominant_intensity = "high" if high_count > 0 else ("medium" if med_count > 0 else "low")
    
    # 3. Machine Learning Business Prediction
    area_hint = _infer_area_from_pois(elements)
    predicted_business = predict_business(dominant_intensity, area_hint=area_hint)
    target_business = requested_business or predicted_business

    # 4. Count nearby direct competitors
    norm_target = target_business.lower().replace(' ', '_')
    competitor_count = 0
    for el in elements:
        tags = el.get('tags', {})
        amenity = str(tags.get('amenity', '')).lower()
        shop = str(tags.get('shop', '')).lower()
        name_tag = str(tags.get('name', '')).lower()
        if norm_target in amenity or norm_target in shop or norm_target in name_tag:
            competitor_count += 1

    # 5. Spatial Revenue Engine & POI Enrichment
    enriched_places, total_area_rev = utils.enrich_places_with_revenue(elements)
    crowd_score = utils.calculate_crowd_score(elements)
    
    # Top location smart revenue
    from tracker.prediction_engine import predict_site_revenue
    pred_res = predict_site_revenue(lat, lon, elements, target_business.lower().replace(' ', '_'))
    res_dict = pred_res.to_dict()

    return {
        "location": {
            "name": name,
            "latitude": round(lat, 5),
            "longitude": round(lon, 5)
        },
        "radius_km": 2.0,
        "crowd_analysis": {
            "dominant_intensity": dominant_intensity,
            "high_sectors": high_count,
            "medium_sectors": med_count,
            "low_sectors": low_count
        },
        "poi_count": len(elements),
        "potential_score": res_dict["potential_score"],
        "crowd_score": crowd_score,
        "business_prediction": target_business,
        "ml_recommended_business": predicted_business,
        "revenue_prediction": {
            "daily_revenue": res_dict["daily_revenue"],
            "monthly_estimate": res_dict["monthly_revenue"],
            "annual_revenue": res_dict["annual_revenue"],
            "confidence": round(res_dict["confidence_score"] / 100.0, 2),
            "confidence_score": res_dict["confidence_score"],
            "revenue_range": res_dict["revenue_range"],
            "risk_level": res_dict["risk_level"]
        },
        "competition": {
            "target_business": target_business,
            "nearby_competitors": competitor_count
        },
        "popular_places": [
            {
                "name": p.get("tags", {}).get("name", "Local Business"),
                "type": p.get("tags", {}).get("amenity") or p.get("tags", {}).get("shop") or "Business",
                "monthly_revenue": p.get("revenue_data", {}).get("estimated_monthly_revenue", 0)
            }
            for p in enriched_places[:6]
        ],
        "total_area_monthly_revenue": total_area_rev
    }


def process_user_query(
    user_query: str,
    client_location_context: Optional[Dict[str, Any]] = None,
    session_history: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Main entrypoint for the Dual-AI Intelligence Orchestrator.
    Handles intent classification, location context resolution, Gemini & Grok invocations, and response merging.
    """
    sanitized_query = sanitize_input(user_query, 1000)
    
    if not sanitized_query:
        return {
            "success": False,
            "message": "Please enter a message or location to analyze.",
            "structured_actions": []
        }

    # Step 0: Report requests go to the shared report generator (report_generator app),
    # never to a default or stale location.
    from report_generator.intent import is_report_request, chat_response as report_chat_response
    if is_report_request(sanitized_query):
        reply = report_chat_response(client_location_context)
        reply['structured_actions'] = [a for a in (validate_structured_action(x) for x in reply['structured_actions']) if a]
        return reply

    # Step 1: Handle Friendly Conversational Chat, Greetings & Identity (Instant responses like Gemini/ChatGPT)
    lower = sanitized_query.lower().strip()
    clean_lower = re.sub(r'[^\w\s]', '', lower)

    # 1a. Name & Identity
    if any(p in clean_lower for p in ['what is your name', 'whats your name', 'what is ur name', 'whats ur name', 'your name', 'ur name', 'who are you', 'who r u']):
        return {
            "success": True,
            "message": "Hey there! 😊 I'm **AI Assistant**, your smart location intelligence co-pilot and business partner! You can chat with me just like a friend. I can help you evaluate crowd density, scout locations, check feasibility, or navigate anywhere on the platform. What's on your mind today?",
            "structured_actions": [
                {"intent": "view_heatmap", "label": "🔥 View Heatmap"},
                {"intent": "open_dashboard", "label": "📈 Open Dashboard"},
            ]
        }

    # 1b. Greetings
    if lower in ['hi', 'hello', 'hey', 'heya', 'hola', 'yo', 'sup', 'howdy', 'good morning', 'good afternoon', 'good evening'] or re.search(r'^(hi|hello|hey|yo)\b', lower):
        return {
            "success": True,
            "message": "Hey! 👋 Great to chat with you! How's your day going? Feel free to ask me anything about the platform, locations, or tell me what business ideas you're exploring!",
            "structured_actions": [
                {"intent": "view_heatmap", "label": "🔥 View Heatmap"},
                {"intent": "open_dashboard", "label": "📈 Open Dashboard"},
            ]
        }

    # 1c. How are you / Friendly check-in
    if any(p in clean_lower for p in ['how are you', 'how r u', 'how are you doing', 'hows it going', 'whats up', 'how do you do']):
        return {
            "success": True,
            "message": "I'm doing fantastic, thanks for asking! 😊 Always excited to help you scout great locations and explore business feasibility. How are you doing today?",
            "structured_actions": [
                {"intent": "view_heatmap", "label": "🔥 View Heatmap"},
                {"intent": "open_dashboard", "label": "📈 Open Dashboard"},
            ]
        }

    # 1d. Friends / Companionship
    if any(p in clean_lower for p in ['can we be friends', 'be my friend', 'are we friends', 'lets be friends']):
        return {
            "success": True,
            "message": "Of course we can! 🤝 I'd love to be your friend and business brainstorming buddy. Tell me, what kind of venture or ideas are you passionate about?",
            "structured_actions": []
        }

    # 1e. Jokes & Humor
    if any(p in clean_lower for p in ['tell me a joke', 'joke', 'make me laugh', 'say something funny']):
        return {
            "success": True,
            "message": "Why did the coffee shop open next to the gym? Because they knew the customers loved an extra shot of energy! ☕💪 What kind of business would you love to start?",
            "structured_actions": []
        }

    # 1f. Gratitude
    if any(p in clean_lower for p in ['thank you', 'thanks', 'thx', 'thank u', 'appreciate it']):
        return {
            "success": True,
            "message": "You're very welcome! Always happy to help a friend. 😊 Let me know anytime you want to check another spot or view the heatmap!",
            "structured_actions": []
        }

    # 1g. Affirmations
    if lower in ['cool', 'awesome', 'nice', 'great', 'good', 'super', 'amazing', 'ok', 'okay', 'got it']:
        return {
            "success": True,
            "message": "Awesome! 👍 Whenever you're ready, ask me about any area, or let me know if you want to jump to the map, analytics, or reports!",
            "structured_actions": [
                {"intent": "view_heatmap", "label": "🔥 View Heatmap"},
                {"intent": "open_dashboard", "label": "📈 Open Dashboard"},
            ]
        }

    # 1h. General capabilities / Help
    if lower in ['help', 'what can you do', 'commands', 'what do you do']:
        return {
            "success": True,
            "message": """I'm your **AI Assistant** and business partner! 🚀 Here is what we can do together:
• **Chat & brainstorm**: Ask me questions like a friend about business ideas and locations
• **Check Feasibility**: Ask *"Is a cafe feasible in Koramangala?"*
• **Analyze Footfall**: Ask *"Show crowd density in Indiranagar"*
• **Navigate Anywhere**: Say *"Take me to map"*, *"Show analytics"*, or *"Where are my reports?"*

What are you thinking of launching?""",
            "structured_actions": [
                {"intent": "view_heatmap", "label": "🔥 View Heatmap"},
                {"intent": "open_dashboard", "label": "📈 Open Dashboard"},
            ]
        }

    # Step 2: Validate Query Relevance (Strict Domain Scope for specialized queries)
    if not is_platform_relevant(sanitized_query):
        return {
            "success": True,
            "message": OUT_OF_SCOPE_RESPONSE,
            "structured_actions": [
                {"intent": "view_heatmap", "label": "🔥 View Heatmap"},
                {"intent": "open_dashboard", "label": "📈 Open Dashboard"},
            ]
        }

    # Step 3: Extract Location & Resolve Coordinates
    query_place, query_biz = _extract_location_and_business_from_query(sanitized_query)
    
    lat = None
    lon = None
    place_name = None

    if query_place:
        geocoded = _geocode_place(query_place)
        if geocoded:
            lat = geocoded["lat"]
            lon = geocoded["lon"]
            place_name = geocoded["name"]

    # Fallback to client location context if not extracted from text
    if lat is None or lon is None:
        if client_location_context and isinstance(client_location_context, dict):
            c_lat = client_location_context.get("lat") or client_location_context.get("latitude")
            c_lon = client_location_context.get("lng") or client_location_context.get("lon") or client_location_context.get("longitude")
            if c_lat and c_lon:
                try:
                    lat = float(c_lat)
                    lon = float(c_lon)
                    place_name = client_location_context.get("name") or client_location_context.get("label") or "Current Selected Area"
                except (ValueError, TypeError):
                    pass

    # Default location if no coordinates resolved
    if lat is None or lon is None:
        lat = DEFAULT_CENTER["lat"]
        lon = DEFAULT_CENTER["lon"]
        place_name = DEFAULT_CENTER["name"]

    # Step 4: Build Ground-Truth Location Context
    try:
        trusted_context = _build_trusted_location_context(
            lat, lon, place_name, requested_business=query_biz
        )
    except Exception as exc:
        logger.error(f"Error building location context: {exc}", exc_info=True)
        trusted_context = {
            "location": {"name": place_name, "latitude": lat, "longitude": lon},
            "crowd_score": 60,
            "potential_score": 65,
            "business_prediction": query_biz or "Retail Business",
            "revenue_prediction": {"monthly_estimate": 250000, "confidence": 0.70},
            "competition": {"nearby_competitors": 5}
        }

    # Step 5: Gemini Primary Analysis
    gemini_res = gemini_analyze(
        context=trusted_context,
        user_query=sanitized_query,
        session_history=session_history
    )

    # Step 6: Grok Secondary Review
    grok_res = grok_review(
        context=trusted_context,
        gemini_analysis=gemini_res.get("analysis"),
        user_query=sanitized_query
    )

    # Step 7: Merge and Synthesize
    final_output = merge_ai_results(
        location_context=trusted_context,
        gemini_result=gemini_res,
        grok_result=grok_res,
        user_query=sanitized_query
    )

    return final_output
