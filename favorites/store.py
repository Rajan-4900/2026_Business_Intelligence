"""
Thin client for the Supabase `favorite_places` table (see supabase/favorites.sql).

Every request is made with the public anon key plus the *user's own* access
token, so Supabase Row Level Security decides what each user can see and
change. Django never holds elevated credentials for this table.
"""
import requests
from django.conf import settings

_TIMEOUT = 8
_COLUMNS = 'id,place_key,name,category,latitude,longitude,address,potential_score,created_at'


class StoreError(Exception):
    def __init__(self, status, message, code=None):
        super().__init__(message)
        self.status = status
        self.code = code


def _request(method, path, token, *, params=None, json=None, prefer=None):
    headers = {
        'apikey': settings.SUPABASE_ANON_KEY,
        'Authorization': f'Bearer {token}',
    }
    if prefer:
        headers['Prefer'] = prefer
    try:
        resp = requests.request(method, f'{settings.SUPABASE_URL}/rest/v1/{path}', headers=headers,
                                params=params, json=json, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        raise StoreError(503, f'Supabase unreachable: {exc}')
    if resp.status_code >= 400:
        try:
            body = resp.json()
        except ValueError:
            body = {}
        raise StoreError(resp.status_code, body.get('message') or resp.text[:200], body.get('code'))
    return resp.json() if resp.content else None


def list_favorites(token):
    return _request('GET', 'favorite_places', token,
                    params={'select': _COLUMNS, 'order': 'created_at.desc'})


def get_by_key(token, place_key):
    rows = _request('GET', 'favorite_places', token,
                    params={'select': _COLUMNS, 'place_key': f'eq.{place_key}'})
    return rows[0] if rows else None


def insert(token, fields):
    """Insert; returns (row, created). An existing (user, place_key) is returned unchanged."""
    rows = _request('POST', 'favorite_places', token, json=fields,
                    params={'on_conflict': 'user_id,place_key', 'select': _COLUMNS},
                    prefer='resolution=ignore-duplicates,return=representation')
    if rows:
        return rows[0], True
    return get_by_key(token, fields['place_key']), False


def delete(token, **filters):
    """Delete matching rows the user owns; returns the number deleted."""
    params = {k: f'eq.{v}' for k, v in filters.items()}
    params['select'] = 'id'
    rows = _request('DELETE', 'favorite_places', token, params=params, prefer='return=representation')
    return len(rows or [])


def community_rows(token, max_rows=5000):
    """Recent favorites from all users, without user ids (SECURITY DEFINER RPC)."""
    return _request('POST', 'rpc/community_favorites', token, json={'max_rows': max_rows})
