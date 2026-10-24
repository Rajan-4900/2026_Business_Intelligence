import json

from django.http import JsonResponse
from django.shortcuts import render
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from . import recommender, store
from .auth import bearer_token_required
from .keys import PLACE_KEY_RE, make_place_key

MAX_FAVORITES_PER_USER = 500  # enforced by the INSERT policy in supabase/favorites.sql


def favorites_page(request):
    """Shell page; the data is loaded by static/js/favorites.js using the Supabase session."""
    return render(request, 'heatmap_app/favorites.html')


class _Invalid(Exception):
    pass


def _parse_place(data):
    """Validate a client-supplied place payload into favorite_places column values."""
    try:
        lat, lon = float(data.get('latitude')), float(data.get('longitude'))
    except (TypeError, ValueError):
        raise _Invalid('latitude and longitude must be numbers')
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise _Invalid('coordinates out of range')
    name = str(data.get('name') or '').strip()[:200]
    if not name:
        raise _Invalid('name is required')
    score = data.get('potential_score')
    if score is not None:
        try:
            score = max(0, min(100, int(round(float(score)))))
        except (TypeError, ValueError):
            score = None
    # Saving from a recommendation echoes the community's key so it merges with
    # everyone else's saves of that place. Anything malformed is recomputed.
    echoed = str(data.get('place_key') or '')
    if PLACE_KEY_RE.match(echoed):
        place_key = echoed
    else:
        place_key = make_place_key(str(data.get('osm_type') or '')[:10],
                                   str(data.get('osm_id') or '')[:20], name, lat, lon)
    return {
        'place_key': place_key,
        'name': name,
        'category': str(data.get('category') or '').strip()[:60],
        'latitude': lat,
        'longitude': lon,
        'address': str(data.get('address') or '').strip()[:255],
        'potential_score': score,
    }


def _json_body(request):
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        raise _Invalid('Invalid JSON')
    if not isinstance(data, dict):
        raise _Invalid('Expected a JSON object')
    return data


def _bad(message, status=400):
    return JsonResponse({'success': False, 'error': message}, status=status)


def _store_error(exc, inserting=False):
    if exc.status == 401 or exc.code == 'PGRST301':
        return _bad('Invalid or expired session', 401)
    if inserting and (exc.status == 403 or exc.code == '42501'):
        # Our only INSERT restriction besides ownership is the per-user cap.
        return _bad(f'Favorite limit of {MAX_FAVORITES_PER_USER} reached', 409)
    if exc.status == 404 or exc.code == 'PGRST202' or exc.code == '42P01':
        return _bad('Favorites table missing: run supabase/favorites.sql in Supabase', 503)
    return _bad('Favorites service error', 502 if exc.status != 503 else 503)


@bearer_token_required
@require_http_methods(['GET', 'POST'])
def favorites_collection(request):
    try:
        if request.method == 'GET':
            return JsonResponse({'success': True, 'favorites': store.list_favorites(request.sb_token)})
        try:
            fields = _parse_place(_json_body(request))
        except _Invalid as exc:
            return _bad(str(exc))
        # Idempotent: saving the same place twice just returns the existing row.
        fav, created = store.insert(request.sb_token, fields)
    except store.StoreError as exc:
        return _store_error(exc, inserting=request.method == 'POST')
    return JsonResponse({'success': True, 'created': created, 'favorite': fav},
                        status=201 if created else 200)


@bearer_token_required
@require_http_methods(['POST'])
def favorite_toggle(request):
    """Heart button endpoint: add if missing, remove if present."""
    try:
        fields = _parse_place(_json_body(request))
    except _Invalid as exc:
        return _bad(str(exc))
    key = fields['place_key']
    try:
        if store.delete(request.sb_token, place_key=key):
            return JsonResponse({'success': True, 'favorited': False, 'place_key': key})
        fav, _ = store.insert(request.sb_token, fields)
    except store.StoreError as exc:
        return _store_error(exc, inserting=True)
    return JsonResponse({'success': True, 'favorited': True, 'place_key': key, 'favorite': fav})


@bearer_token_required
@require_http_methods(['DELETE'])
def favorite_detail(request, pk):
    # RLS limits the delete to the caller's rows, so another user's id looks like a missing one.
    try:
        deleted = store.delete(request.sb_token, id=pk)
    except store.StoreError as exc:
        return _store_error(exc)
    if not deleted:
        return _bad('Favorite not found', 404)
    return JsonResponse({'success': True})


def _rows_for_recommender(rows, saver=None):
    """Adapt PostgREST rows to recommender input (aware datetimes, a saver id per row)."""
    out = []
    for i, r in enumerate(rows):
        # Community rows carry no user id. Each row is a distinct saver of its
        # place (UNIQUE (user_id, place_key)), so the row index stands in for one.
        out.append({**r, 'created_at': parse_datetime(r['created_at']), 'user_id': saver or f'r{i}'})
    return out


@bearer_token_required
@require_http_methods(['GET'])
def recommendations(request):
    """Popular + personalised picks. Optional ?lat=&lon=&limit= (limit 1-20)."""
    try:
        lat = float(request.GET['lat']) if 'lat' in request.GET else None
        lon = float(request.GET['lon']) if 'lon' in request.GET else None
        limit = max(1, min(20, int(request.GET.get('limit', 8))))
    except ValueError:
        return _bad('lat, lon and limit must be numbers')
    if (lat is None) != (lon is None) or (lat is not None and not (
            -90 <= lat <= 90 and -180 <= lon <= 180)):
        return _bad('Provide a valid lat and lon together')

    try:
        mine = _rows_for_recommender(store.list_favorites(request.sb_token), saver='me')
        community = _rows_for_recommender(store.community_rows(request.sb_token))
    except store.StoreError as exc:
        return _store_error(exc)
    picks = recommender.recommend(mine, community, lat=lat, lon=lon, limit=limit)
    return JsonResponse({'success': True, 'personalized': bool(mine), 'recommendations': picks})
