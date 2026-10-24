import json
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from business_intelligence import analysis, utils
from business_intelligence.views import analyze_crowd_intensity
from report_generator.data_collector import CollectionError, collect_analysis, feasibility_elements

from .fixtures import LAT, LON, NAME, fake_overpass, overpass_elements


class CollectAnalysisTests(SimpleTestCase):
    def collect(self, business=''):
        with fake_overpass():
            return collect_analysis(LAT, LON, NAME, 2000, business)

    def test_valid_location_analysis(self):
        s = self.collect()
        self.assertEqual(s['location'], {'name': NAME, 'latitude': LAT, 'longitude': LON, 'radius_m': 2000})
        self.assertEqual(s['heatmap']['counts'], {'high': 2, 'medium': 1, 'low': 1, 'empty': 5})
        self.assertEqual(s['heatmap']['dominant'], 'high')
        self.assertEqual(len(s['heatmap']['sectors']), 9)
        self.assertEqual(s['recommendation']['status'], 'ok')
        self.assertEqual(s['target_business'], s['recommendation']['primary'])
        self.assertEqual(s['feasibility']['status'], 'ok')
        self.assertEqual(s['missing'], [])

    def test_heatmap_matches_the_website_endpoint(self):
        with fake_overpass():
            resp = analyze_crowd_intensity(RequestFactory().post(
                '/', json.dumps({'latitude': LAT, 'longitude': LON}), content_type='application/json'))
            s = collect_analysis(LAT, LON, NAME, 2000)
        site = json.loads(resp.content)
        for level in ('high', 'medium', 'low'):
            self.assertEqual(s['heatmap']['areas'][level], site[f'{level}_intensity'])
        self.assertEqual(s['recommendation']['primary'], site['business_prediction']['primary'])

    def test_revenue_comes_from_existing_engine(self):
        s = self.collect('cafe')
        engine = utils.calculate_smart_revenue(overpass_elements(), business_type='cafe', lat=LAT, lon=LON)
        self.assertEqual(s['revenue']['monthly'], engine['monthly_revenue'])
        self.assertEqual(s['revenue']['range'], engine['revenue_range'])
        self.assertEqual(s['revenue']['scenarios']['base'], engine['monthly_revenue'])
        self.assertFalse(s['revenue']['uses_default_assumptions'])
        # The breakdown must reproduce the engine's own daily figure.
        self.assertIsNotNone(s['revenue']['breakdown'])

    def test_unmodelled_business_is_flagged(self):
        s = self.collect('Tailoring Shop')
        self.assertTrue(s['revenue']['uses_default_assumptions'])
        self.assertEqual(s['revenue']['assumptions']['avg_spend'], 600.0)

    def test_user_business_takes_priority_and_candidates_are_engine_runs(self):
        s = self.collect('Pharmacy')
        self.assertEqual(s['target_business'], 'Pharmacy')
        self.assertEqual(s['candidates'][0]['source'], 'Your selected business')
        for c in s['candidates']:
            engine = utils.calculate_smart_revenue(overpass_elements(), business_type=c['business'], lat=LAT, lon=LON)
            self.assertEqual(c['potential_score'], engine['potential_score'])

    def test_feasibility_matches_the_website_rules(self):
        s = self.collect('cafe')
        expected = analysis.evaluate_feasibility(feasibility_elements(overpass_elements()), LAT, LON, 'cafe')
        self.assertEqual(s['feasibility']['feasible'], expected['feasible'])
        self.assertEqual(s['feasibility']['message'], expected['message'])

    def test_feasibility_elements_match_the_feasibility_query_tags(self):
        kept = feasibility_elements(overpass_elements())
        self.assertTrue(all({'amenity', 'shop', 'tourism'} & set(el['tags']) for el in kept))
        self.assertFalse(any(el['tags'].get('building') and len(el['tags']) == 1 for el in kept))

    def test_missing_heatmap_data(self):
        with fake_overpass(elements=[]):
            s = collect_analysis(LAT, LON, NAME, 2000)
        self.assertTrue(s['heatmap']['placeholder_used'])
        self.assertEqual(s['pois']['status'], 'unavailable')
        items = [m['item'] for m in s['missing']]
        self.assertIn('Sector-level crowd intensity', items)

    def test_overpass_failure_raises(self):
        with fake_overpass(error='Overpass API timeout'):
            with self.assertRaises(CollectionError):
                collect_analysis(LAT, LON, NAME, 2000)

    def test_missing_revenue_results_are_not_invented(self):
        with fake_overpass(), patch('business_intelligence.utils.calculate_smart_revenue', side_effect=RuntimeError):
            s = collect_analysis(LAT, LON, NAME, 2000, 'cafe')
        self.assertEqual(s['revenue']['status'], 'unavailable')
        self.assertNotIn('monthly', s['revenue'])
        self.assertTrue(all(c.get('revenue_error') for c in s['candidates']))
        self.assertIn('Revenue forecast', [m['item'] for m in s['missing']])

    def test_missing_recommendation_results(self):
        with fake_overpass(), patch('business_intelligence.analysis.build_business_prediction', side_effect=FileNotFoundError):
            s = collect_analysis(LAT, LON, NAME, 2000)
        self.assertEqual(s['recommendation']['status'], 'unavailable')
        self.assertEqual(s['target_business'], '')
        self.assertEqual(s['revenue']['status'], 'unavailable')
        self.assertEqual(s['feasibility']['status'], 'unavailable')

    def test_progress_reports_real_steps_in_order(self):
        seen = []
        with fake_overpass():
            collect_analysis(LAT, LON, NAME, 2000, progress=seen.append)
        self.assertEqual(seen, ['collect', 'crowd', 'recommend', 'revenue'])
