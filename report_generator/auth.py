"""
Report endpoints need to know *who* the caller is (reports are private), not
just that a token is present. favorites/ forwards the token to Supabase and
lets Row Level Security decide; here the rows live in Django's database, so
we ask Supabase Auth to verify the token and give us the user's id.

The verified id is cached for a minute under a hash of the token (the token
itself is never stored).
"""
import hashlib
import logging
import re
from functools import wraps

import requests
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse

logger = logging.getLogger(__name__)

_TIMEOUT = 6
_CACHE_SECONDS = 60
_USER_ID_RE = re.compile(r'^[A-Za-z0-9-]{8,64}$')


class AuthError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def verify_supabase_token(token):
    """Return the Supabase user id for `token`, or raise AuthError."""
    cache_key = 'report_auth_' + hashlib.sha256(token.encode()).hexdigest()
    cached = cache.get(cache_key)
    if cached:
        return cached
    try:
        resp = requests.get(
            f'{settings.SUPABASE_URL}/auth/v1/user',
            headers={'apikey': settings.SUPABASE_ANON_KEY, 'Authorization': f'Bearer {token}'},
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning('Supabase auth unreachable: %s', exc)
        raise AuthError(503, 'Authentication service unavailable. Please try again.')
    if resp.status_code in (401, 403):
        raise AuthError(401, 'Invalid or expired session. Please sign in again.')
    if resp.status_code >= 400:
        raise AuthError(503, 'Authentication service unavailable. Please try again.')
    try:
        user_id = str(resp.json().get('id') or '')
    except ValueError:
        user_id = ''
    if not _USER_ID_RE.match(user_id):
        raise AuthError(401, 'Invalid or expired session. Please sign in again.')
    cache.set(cache_key, user_id, _CACHE_SECONDS)
    return user_id


def supabase_user_required(view):
    """Decorator: 401 unless the Bearer token verifies. Sets request.report_owner_id.

    Unlike favorites.auth.bearer_token_required this does *not* mark the view
    CSRF-exempt: the dashboard sends X-CSRFToken as well, so both checks apply.
    """
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        header = request.META.get('HTTP_AUTHORIZATION', '')
        token = header[7:].strip() if header.startswith('Bearer ') else ''
        if len(token) < 20 or len(token) > 4096:
            return JsonResponse({'success': False, 'error': 'Sign in required'}, status=401)
        try:
            request.report_owner_id = verify_supabase_token(token)
        except AuthError as exc:
            return JsonResponse({'success': False, 'error': str(exc)}, status=exc.status)
        return view(request, *args, **kwargs)

    return wrapper
