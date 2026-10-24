"""
The browser keeps the Supabase session; Django never sees a logged-in
`request.user`. API calls send `Authorization: Bearer <access_token>`, which
favorites.store forwards to Supabase so that Row Level Security, not Django,
enforces who owns which rows. Supabase rejects bad or expired tokens with a
401, which the views pass back to the client.
"""
from functools import wraps

from django.http import JsonResponse


def bearer_token_required(view):
    """Decorator: 401 unless a Bearer token is present. Sets request.sb_token.

    The token is a header, not a cookie, so a cross-site request can't carry it.
    That's why these endpoints are exempt from CSRF checks.
    """
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        header = request.META.get('HTTP_AUTHORIZATION', '')
        token = header[7:].strip() if header.startswith('Bearer ') else ''
        if len(token) < 20:
            return JsonResponse({'success': False, 'error': 'Sign in required'}, status=401)
        request.sb_token = token
        return view(request, *args, **kwargs)

    wrapper.csrf_exempt = True
    return wrapper
