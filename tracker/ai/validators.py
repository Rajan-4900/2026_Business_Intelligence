"""
Input sanitization, scope validation, security filtering, and action validators.
"""

import re
from typing import Dict, Any, Optional, List

# Allowed structured intents that the frontend can safely execute
SAFE_INTENTS = {
    'analyze_location',
    'check_feasibility',
    'view_heatmap',
    'find_alternative_locations',
    'compare_locations',
    'open_dashboard',
    'open_form',
    'find_popular_places',
    'generate_report',
}

# Sensitive keys that must NEVER be passed to external AI models
SENSITIVE_KEY_PATTERNS = re.compile(
    r'(password|secret|api[_-]?key|token|auth|credentials|private|session|email|phone)',
    re.IGNORECASE
)

# Common out-of-scope intent keywords
OFF_TOPIC_PATTERNS = [
    r'\b(write|create|code|program|script)\s+(a\s+)?(python|java|c\+\+|javascript|html|react|rust|golang|game|app|discord|bot)\b',
    r'\b(who\s+won|score\s+of|cricket|football|match|fifa|ipl|nba|tennis)\b',
    r'\b(recipe\s+for|cook|bake|ingredients\s+for)\b',
    r'\b(tell\s+me\s+a\s+joke|write\s+(a\s+)?poem|write\s+(a\s+)?story|sing\s+a\s+song)\b',
    r'\b(solve\s+this\s+math|differential\s+equation|integral|calculus|algebra\s+problem)\b',
    r'\b(who\s+is\s+the\s+president|politics|election\s+result)\b',
]


def is_platform_relevant(query: str) -> bool:
    """
    Determine if a user query is within the domain of location analysis,
    business intelligence, or website functionality.
    """
    if not query or not query.strip():
        return False
        
    lower_query = query.strip().lower()
    
    # 1. Check for clear off-topic patterns
    for pattern in OFF_TOPIC_PATTERNS:
        if re.search(pattern, lower_query):
            # If it ALSO explicitly asks about business location / feasibility, allow it
            if not any(k in lower_query for k in ['location', 'place', 'business', 'shop', 'store', 'cafe', 'revenue', 'heatmap']):
                return False

    # 2. Greetings, friendly chat and self-identity queries are relevant (assistant answers like a friend)
    friendly_prompts = [
        'hi', 'hello', 'hey', 'help', 'what can you do', 'who are you', 'how does this work',
        'name', 'your name', 'ur name', 'how are you', 'joke', 'friend', 'friends', 'thanks',
        'thank you', 'cool', 'awesome', 'nice', 'great'
    ]
    if any(g in lower_query for g in friendly_prompts) and len(lower_query.split()) < 12:
        return True
        
    # 3. Platform keywords
    platform_keywords = [
        'open', 'start', 'business', 'shop', 'store', 'cafe', 'restaurant', 'pharmacy',
        'supermarket', 'gym', 'salon', 'boutique', 'bakery', 'hotel', 'location',
        'place', 'area', 'city', 'zone', 'heatmap', 'crowd', 'density', 'footfall',
        'revenue', 'feasibility', 'feasible', 'profit', 'competitor', 'competition',
        'alternative', 'compare', 'analyze', 'search', 'bangalore', 'mumbai', 'delhi',
        'bengaluru', 'hyderabad', 'chennai', 'pune', 'kolkata', 'indiranagar',
        'koramangala', 'whitefield', 'dashboard', 'potential', 'score', 'cqi'
    ]
    
    if any(keyword in lower_query for keyword in platform_keywords):
        return True
        
    # 4. Short queries (under 5 words) that might be location names (e.g. "Koramangala", "MG Road")
    words = lower_query.split()
    if len(words) <= 4:
        return True
        
    return False


def sanitize_input(query: str, max_length: int = 1000) -> str:
    """
    Sanitize raw user input, limit length, and strip control characters.
    """
    if not query:
        return ""
    cleaned = query.strip()
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    # Remove non-printable control characters (except newline, tab)
    cleaned = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', cleaned)
    return cleaned


def sanitize_context_for_ai(context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Recursively sanitize context dictionary to ensure NO credentials, tokens,
    passwords, or personal user info are sent to external AI providers.
    """
    if not context or not isinstance(context, dict):
        return {}
        
    clean_dict: Dict[str, Any] = {}
    for key, value in context.items():
        if SENSITIVE_KEY_PATTERNS.search(str(key)):
            continue
            
        if isinstance(value, dict):
            clean_dict[key] = sanitize_context_for_ai(value)
        elif isinstance(value, list):
            clean_list = []
            for item in value:
                if isinstance(item, dict):
                    clean_list.append(sanitize_context_for_ai(item))
                elif isinstance(item, (str, int, float, bool)) and not SENSITIVE_KEY_PATTERNS.search(str(item)):
                    clean_list.append(item)
            clean_dict[key] = clean_list
        elif isinstance(value, (str, int, float, bool)) or value is None:
            clean_dict[key] = value
            
    return clean_dict


def validate_structured_action(action: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Validate that an AI-generated structured action adheres to safe predefined schemas.
    Never permits arbitrary JavaScript or unexpected parameters.
    """
    if not isinstance(action, dict):
        return None
        
    intent = str(action.get('intent', '')).strip().lower()
    if intent not in SAFE_INTENTS:
        return None
        
    valid_action: Dict[str, Any] = {'intent': intent}
    
    # Optional allowed fields
    if 'location' in action and isinstance(action['location'], str):
        valid_action['location'] = sanitize_input(action['location'], 150)
    if 'business_type' in action and isinstance(action['business_type'], str):
        valid_action['business_type'] = sanitize_input(action['business_type'], 100)
    if 'locations' in action and isinstance(action['locations'], list):
        valid_action['locations'] = [sanitize_input(str(loc), 150) for loc in action['locations'][:5]]
    if intent == 'generate_report' and action.get('auto_run') is True:
        valid_action['auto_run'] = True
    if 'label' in action and isinstance(action['label'], str):
        valid_action['label'] = sanitize_input(action['label'], 60)
    else:
        # Default user-friendly button label
        labels = {
            'analyze_location': '📊 Analyze Location',
            'check_feasibility': '🏢 Check Feasibility',
            'view_heatmap': '🔥 View Heatmap',
            'find_alternative_locations': '📍 Find Better Zones',
            'compare_locations': '⚖️ Compare Locations',
            'open_dashboard': '📈 Open Dashboard',
            'open_form': '📝 Submit Business Info',
            'find_popular_places': '🎯 Popular Places Radar',
            'generate_report': '📄 Generate PDF report',
        }
        valid_action['label'] = labels.get(intent, 'Action')
        
    return valid_action
