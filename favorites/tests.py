from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import requests

import itertools

from django.test import SimpleTestCase, override_settings

from . import recommender
from . import store
from .keys import make_place_key

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def row(key, user, category='cafe', lat=12.97, lon=77.59, age_days=0, score=None, name=None):
    return {'place_key': key, 'user_id': user, 'name': name or key, 'category': category,
            'latitude': lat, 'longitude': lon, 'address': '', 'potential_score': score,
            'created_at': NOW - timedelta(days=age_days)}


class RecommenderTests(SimpleTestCase):
    def test_excludes_places_user_already_saved(self):
        mine = [row('a', 'u1')]
        community = mine + [row('a', 'u2'), row('b', 'u2')]
        picks = recommender.recommend(mine, community, now=NOW)
        self.assertEqual([p['place_key'] for p in picks], ['b'])

    def test_more_savers_rank_higher_when_otherwise_equal(self):
        community = [row('a', 'u2'), row('b', 'u2'), row('b', 'u3'), row('b', 'u4')]
        picks = recommender.recommend([], community, now=NOW)
        self.assertEqual(picks[0]['place_key'], 'b')
        self.assertEqual(picks[0]['savers'], 3)

    def test_old_saves_decay(self):
        community = [row('old', 'u2', age_days=400), row('old', 'u3', age_days=400),
                     row('new', 'u4', age_days=1)]
        picks = recommender.recommend([], community, now=NOW)
        self.assertEqual(picks[0]['place_key'], 'new')

    def test_category_affinity_boosts_matching_category(self):
        mine = [row('m1', 'me', category='cafe'), row('m2', 'me', category='cafe')]
        community = mine + [row('cafe2', 'u2', category='cafe'), row('gym', 'u2', category='gym')]
        picks = recommender.recommend(mine, community, now=NOW)
        self.assertEqual(picks[0]['place_key'], 'cafe2')
        self.assertTrue(any('often save' in r for r in picks[0]['reasons']))

    def test_proximity_to_supplied_location_wins(self):
        community = [row('near', 'u2', lat=12.97, lon=77.59), row('far', 'u3', lat=28.6, lon=77.2)]
        picks = recommender.recommend([], community, lat=12.98, lon=77.60, now=NOW)
        self.assertEqual(picks[0]['place_key'], 'near')

    def test_cold_start_without_any_signal_still_returns_results(self):
        picks = recommender.recommend([], [row('a', 'u2')], now=NOW)
        self.assertEqual(len(picks), 1)
        self.assertGreater(picks[0]['score'], 0)

    def test_empty_community(self):
        self.assertEqual(recommender.recommend([], [], now=NOW), [])

    def test_limit(self):
        community = [row(f'p{i}', f'u{i}') for i in range(10)]
        self.assertEqual(len(recommender.recommend([], community, limit=3, now=NOW)), 3)


class PlaceKeyTests(SimpleTestCase):
    def test_osm_key(self):
        self.assertEqual(make_place_key('node', '42', 'X', 1.0, 2.0), 'osm:node:42')

    def test_geo_fallback_is_stable_and_rounded(self):
        a = make_place_key('', '', 'Blue Tokai!', 12.971599, 77.594601)
        b = make_place_key('', '', 'blue  tokai', 12.97162, 77.59458)
        self.assertEqual(a, b)


class FakeStore:
    """In-memory stand-in for Supabase that applies the same rules as the RLS
    policies: a token maps to a user, and users only see and delete their own rows."""

    def __init__(self):
        self.rows = []
        self.ids = itertools.count(1)

    def _uid(self, token):
        if token.startswith('bad'):
            raise store.StoreError(401, 'JWT expired', 'PGRST301')
        return token.split(':')[0]

    def list_favorites(self, token):
        uid = self._uid(token)
        return [{k: v for k, v in r.items() if k != 'user_id'} for r in reversed(self.rows) if r['user_id'] == uid]

    def insert(self, token, fields):
        uid = self._uid(token)
        for r in self.rows:
            if r['user_id'] == uid and r['place_key'] == fields['place_key']:
                return {k: v for k, v in r.items() if k != 'user_id'}, False
        row = {'id': next(self.ids), 'user_id': uid, 'created_at': '2026-01-01T00:00:00.12345+00:00', **fields}
        self.rows.append(row)
        return {k: v for k, v in row.items() if k != 'user_id'}, True

    def delete(self, token, **filters):
        uid = self._uid(token)
        keep = [r for r in self.rows if not (r['user_id'] == uid and all(r[k] == v for k, v in filters.items()))]
        n = len(self.rows) - len(keep)
        self.rows = keep
        return n

    def community_rows(self, token, max_rows=5000):
        self._uid(token)
        return [{k: v for k, v in r.items() if k not in ('user_id', 'id')} for r in self.rows]


PLACE = {'name': 'Cafe One', 'category': 'cafe', 'latitude': 12.97, 'longitude': 77.59,
         'osm_type': 'node', 'osm_id': 1, 'potential_score': 81}


def bearer(user):
    return {'HTTP_AUTHORIZATION': f'Bearer {user}:' + 'x' * 30}


@override_settings(SECURE_SSL_REDIRECT=False)  # prod default would 301 every test request
class FavoritesApiTests(SimpleTestCase):
    def setUp(self):
        self.fake = FakeStore()
        for name in ('list_favorites', 'insert', 'delete', 'community_rows'):
            patcher = patch(f'favorites.store.{name}', getattr(self.fake, name))
            patcher.start()
            self.addCleanup(patcher.stop)

    def post(self, url, body, user='alice'):
        return self.client.post(url, body, content_type='application/json', **bearer(user))

    def get(self, url, user='alice'):
        return self.client.get(url, **bearer(user))

    def test_requires_token(self):
        self.assertEqual(self.client.get('/api/favorites/').status_code, 401)
        self.assertEqual(self.client.get('/api/favorites/recommendations/').status_code, 401)

    def test_expired_token_from_supabase_is_401(self):
        self.assertEqual(self.get('/api/favorites/', user='bad').status_code, 401)

    def test_add_is_idempotent_and_listed(self):
        self.assertEqual(self.post('/api/favorites/', PLACE).status_code, 201)
        self.assertEqual(self.post('/api/favorites/', PLACE).status_code, 200)
        favs = self.get('/api/favorites/').json()['favorites']
        self.assertEqual([f['place_key'] for f in favs], ['osm:node:1'])

    def test_validation(self):
        self.assertEqual(self.post('/api/favorites/', {**PLACE, 'latitude': 999}).status_code, 400)
        self.assertEqual(self.post('/api/favorites/', {**PLACE, 'name': ' '}).status_code, 400)
        self.assertEqual(self.post('/api/favorites/', '[]').status_code, 400)

    def test_malformed_echoed_key_is_recomputed(self):
        fav = self.post('/api/favorites/', {**PLACE, 'place_key': 'evil key'}).json()['favorite']
        self.assertEqual(fav['place_key'], 'osm:node:1')

    def test_toggle(self):
        self.assertTrue(self.post('/api/favorites/toggle/', PLACE).json()['favorited'])
        self.assertFalse(self.post('/api/favorites/toggle/', PLACE).json()['favorited'])
        self.assertEqual(self.fake.rows, [])

    def test_users_are_isolated(self):
        fav_id = self.post('/api/favorites/', PLACE, user='alice').json()['favorite']['id']
        self.assertEqual(self.get('/api/favorites/', user='bob').json()['favorites'], [])
        resp = self.client.delete(f'/api/favorites/{fav_id}/', **bearer('bob'))
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(len(self.fake.rows), 1)
        resp = self.client.delete(f'/api/favorites/{fav_id}/', **bearer('alice'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.fake.rows, [])

    def test_recommendations_use_other_users_favorites(self):
        self.post('/api/favorites/', PLACE, user='alice')
        self.post('/api/favorites/', {**PLACE, 'osm_id': 2, 'name': 'Mine'}, user='bob')
        body = self.get('/api/favorites/recommendations/?limit=5', user='bob').json()
        self.assertTrue(body['personalized'])
        self.assertEqual([r['name'] for r in body['recommendations']], ['Cafe One'])

    def test_recommendation_param_validation(self):
        self.assertEqual(self.get('/api/favorites/recommendations/?lat=12').status_code, 400)
        self.assertEqual(self.get('/api/favorites/recommendations/?lat=x&lon=1').status_code, 400)

    def test_missing_table_gives_actionable_error(self):
        with patch('favorites.store.list_favorites',
                   side_effect=store.StoreError(404, 'relation does not exist', '42P01')):
            resp = self.get('/api/favorites/')
        self.assertEqual(resp.status_code, 503)
        self.assertIn('supabase/favorites.sql', resp.json()['error'])


@override_settings(SUPABASE_URL='https://proj.supabase.co', SUPABASE_ANON_KEY='anon-key')
class StoreRequestTests(SimpleTestCase):
    """The store must send the user's token (so RLS applies), never anything privileged."""

    def _resp(self, status=200, body=b'[]'):
        r = requests.Response()
        r.status_code, r._content = status, body
        return r

    def test_insert_forwards_user_token_and_upserts_without_overwrite(self):
        with patch('favorites.store.requests.request', return_value=self._resp(201, b'[{"id": 1}]')) as req:
            row, created = store.insert('user-token', {'place_key': 'osm:node:1'})
        self.assertEqual((row, created), ({'id': 1}, True))
        method, url = req.call_args.args
        kw = req.call_args.kwargs
        self.assertEqual((method, url), ('POST', 'https://proj.supabase.co/rest/v1/favorite_places'))
        self.assertEqual(kw['headers']['Authorization'], 'Bearer user-token')
        self.assertEqual(kw['headers']['apikey'], 'anon-key')
        self.assertIn('ignore-duplicates', kw['headers']['Prefer'])
        self.assertEqual(kw['params']['on_conflict'], 'user_id,place_key')

    def test_errors_carry_status_and_code(self):
        body = b'{"code": "PGRST301", "message": "JWT expired"}'
        with patch('favorites.store.requests.request', return_value=self._resp(401, body)):
            with self.assertRaises(store.StoreError) as ctx:
                store.list_favorites('t')
        self.assertEqual((ctx.exception.status, ctx.exception.code), (401, 'PGRST301'))

    def test_network_failure_is_503(self):
        with patch('favorites.store.requests.request', side_effect=requests.ConnectionError('down')):
            with self.assertRaises(store.StoreError) as ctx:
                store.community_rows('t')
        self.assertEqual(ctx.exception.status, 503)
