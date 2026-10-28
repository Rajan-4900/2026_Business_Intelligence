from django.test import TestCase
from business_intelligence.prediction_engine import (
    FeatureExtractor,
    HuffModel,
    ExtendedHuffModel,
    RevenuePredictor,
    predict_site_revenue
)
from business_intelligence import utils

class PredictionEngineTestCase(TestCase):
    def setUp(self):
        self.target_lat = 19.0760
        self.target_lon = 72.8777
        self.business_type = 'cafe'
        
        # Construct mock OSM elements
        self.mock_elements = [
            # Target location (or very close to it)
            {
                'type': 'node',
                'lat': 19.0760,
                'lon': 72.8777,
                'tags': {'amenity': 'cafe', 'name': 'Target Cafe'}
            },
            # Competitor cafe (400 meters away)
            {
                'type': 'node',
                'lat': 19.0790,
                'lon': 72.8777,
                'tags': {'amenity': 'cafe', 'name': 'Competitor Cafe'}
            },
            # Residential building
            {
                'type': 'way',
                'center': {'lat': 19.0750, 'lon': 72.8760},
                'tags': {'building': 'residential'}
            },
            # Office building
            {
                'type': 'way',
                'center': {'lat': 19.0770, 'lon': 72.8790},
                'tags': {'building': 'office', 'office': 'it'}
            },
            # Metro station
            {
                'type': 'node',
                'lat': 19.0740,
                'lon': 72.8750,
                'tags': {'railway': 'subway_entrance', 'subway': 'yes'}
            },
            # Bus stop
            {
                'type': 'node',
                'lat': 19.0765,
                'lon': 72.8765,
                'tags': {'highway': 'bus_stop'}
            },
            # Parking
            {
                'type': 'node',
                'lat': 19.0755,
                'lon': 72.8785,
                'tags': {'amenity': 'parking'}
            },
            # Footpath
            {
                'type': 'way',
                'center': {'lat': 19.0762, 'lon': 72.8772},
                'tags': {'highway': 'footway'}
            },
            # Intersection (crossing)
            {
                'type': 'node',
                'lat': 19.0761,
                'lon': 72.8775,
                'tags': {'highway': 'crossing'}
            },
            # Tourism spot
            {
                'type': 'node',
                'lat': 19.0730,
                'lon': 72.8720,
                'tags': {'tourism': 'viewpoint'}
            }
        ]

    def test_feature_extraction(self):
        extractor = FeatureExtractor(self.target_lat, self.target_lon, self.business_type)
        features = extractor.extract_features(self.mock_elements)
        
        # Verify all 11 features are engineered and strongly typed
        self.assertGreater(features.expected_visitors, 0.0)
        self.assertGreater(features.accessibility_score, 0.0)
        self.assertGreater(features.business_attraction_score, 0.0)
        self.assertGreater(features.competition_score, 0.0)
        self.assertGreater(features.income_proxy, 0.0)
        self.assertGreater(features.demand_supply_ratio, 0.0)
        self.assertGreater(features.transit_score, 0.0)
        self.assertGreater(features.walkability_score, 0.0)
        self.assertGreater(features.parking_score, 0.0)
        self.assertGreater(features.area_diversity_score, 0.0)
        
        # Check Customer Mix proportions sum close to 1
        mix = features.customer_mix
        total_mix = sum(mix.values())
        self.assertAlmostEqual(total_mix, 1.0, places=2)
        self.assertIn('students', mix)
        self.assertIn('professionals', mix)
        self.assertIn('families', mix)
        self.assertIn('tourists', mix)
        self.assertIn('residents', mix)

    def test_huff_model(self):
        huff = HuffModel(self.target_lat, self.target_lon, self.business_type)
        metrics = huff.compute_huff_metrics(
            elements=self.mock_elements,
            accessibility_score=80.0,
            business_attraction_score=75.0,
            area_diversity_score=60.0,
            income_proxy=70.0,
            expected_visitors=500.0
        )
        
        # Check choice probability boundaries
        self.assertTrue(0.0 < metrics.choice_probability <= 1.0)
        self.assertTrue(0.0 < metrics.market_share <= 1.0)
        self.assertGreater(metrics.store_attraction, 0.0)
        self.assertGreater(metrics.distance_decay, 0.0)
        self.assertEqual(len(metrics.time_aware_visits), 24)

    def test_extended_huff(self):
        extended = ExtendedHuffModel(self.business_type)
        metrics = extended.compute_extended_metrics(
            elements=self.mock_elements,
            market_share=0.45,
            expected_visitors=500.0,
            accessibility_score=80.0,
            competition_score=35.0,
            demand_supply_ratio=1.4
        )
        
        # Verify competition adjustment discount factor
        self.assertTrue(0.0 < metrics.competition_adjustment <= 1.0)
        self.assertTrue(0.0 < metrics.business_performance <= 1.0)
        self.assertGreater(metrics.retail_turnover, 0.0)
        self.assertTrue(0.0 < metrics.revenue_confidence <= 100.0)

    def test_revenue_predictor(self):
        extractor = FeatureExtractor(self.target_lat, self.target_lon, self.business_type)
        features = extractor.extract_features(self.mock_elements)
        
        predictor = RevenuePredictor()
        res = predictor.predict(
            features=features,
            elements=self.mock_elements,
            business_type=self.business_type,
            target_lat=self.target_lat,
            target_lon=self.target_lon
        )
        
        # Verify revenue intervals align
        self.assertAlmostEqual(res.weekly_revenue, res.daily_revenue * 7.0, places=2)
        self.assertAlmostEqual(res.monthly_revenue, res.daily_revenue * 30.0, places=2)
        self.assertAlmostEqual(res.annual_revenue, res.daily_revenue * 365.0, places=2)
        
        # Verify output formats
        self.assertTrue(0 <= res.potential_score <= 100)
        self.assertTrue(0 <= res.confidence_score <= 100)
        self.assertLess(res.revenue_range[0], res.revenue_range[1])
        self.assertIn(res.business_health, ['Strong', 'Moderate', 'Weak'])
        self.assertIn(res.risk_level, ['Low', 'Medium', 'High'])
        self.assertGreater(len(res.top_positive_factors), 0)
        self.assertGreater(len(res.top_negative_factors), 0)
        self.assertGreater(len(res.actionable_recommendations), 0)

    def test_backward_compatibility_wrappers(self):
        # 1. Test calculate_smart_revenue wrapper
        result = utils.calculate_smart_revenue(
            self.mock_elements,
            business_type=self.business_type,
            lat=self.target_lat,
            lon=self.target_lon
        )
        
        # Verify legacy keys exist
        self.assertIn('estimated_daily_revenue', result)
        self.assertIn('estimated_monthly_revenue', result)
        self.assertIn('peak_hour_revenue', result)
        self.assertIn('potential_score', result)
        self.assertIn('business_health', result)
        self.assertIn('overload_risk', result)
        self.assertIn('recommendations', result)
        
        # Verify new keys exist
        self.assertIn('hourly_revenue', result)
        self.assertIn('daily_revenue', result)
        self.assertIn('weekly_revenue', result)
        self.assertIn('monthly_revenue', result)
        self.assertIn('annual_revenue', result)
        self.assertIn('confidence_score', result)
        self.assertIn('revenue_range', result)
        self.assertIn('risk_level', result)
        self.assertIn('top_positive_factors', result)
        self.assertIn('top_negative_factors', result)
        
        # 2. Test enrich_places_with_revenue wrapper
        enriched_places, total_revenue = utils.enrich_places_with_revenue(self.mock_elements)
        self.assertEqual(len(enriched_places), len(self.mock_elements))
        self.assertGreater(total_revenue, 0.0)
        
        # Check first place has been enriched with revenue_data
        first_place = enriched_places[0]
        self.assertIn('revenue_data', first_place)
        self.assertIn('estimated_monthly_revenue', first_place['revenue_data'])
        
        # 3. Test generate_best_location_candidates wrapper
        candidates = utils.generate_best_location_candidates(
            self.target_lat,
            self.target_lon,
            self.mock_elements,
            top_n=2
        )
        self.assertLessEqual(len(candidates), 2)
        if candidates:
            first_cand = candidates[0]
            self.assertIn('score', first_cand)
            self.assertIn('estimated_revenue', first_cand)
            self.assertIn('feasibility_factors', first_cand)
            self.assertIn('revenue_data', first_cand)


class LocationIntelligenceAndRecommendationsTestCase(TestCase):
    def setUp(self):
        self.lat = 12.9716
        self.lon = 77.5946
        self.location_name = "MG Road, Bengaluru"
        self.radius = 5000

    def test_fallback_spatial_pois_generation(self):
        from business_intelligence.analysis import generate_fallback_spatial_pois, _haversine_distance_m
        data = generate_fallback_spatial_pois(self.lat, self.lon, self.radius)
        self.assertFalse(data.get('is_live'))
        self.assertEqual(data.get('data_source'), 'Estimated crowd density based on available signals')
        self.assertEqual(data.get('data_quality'), 'Signal-based estimate')

        elements = data.get('elements', [])
        self.assertGreater(len(elements), 0)
        for el in elements:
            self.assertIn('lat', el)
            self.assertIn('lon', el)
            self.assertIn('tags', el)
            dist = _haversine_distance_m(self.lat, self.lon, el['lat'], el['lon'])
            self.assertLessEqual(dist, self.radius + 50, "Generated POI should be within 5 km analysis zone")

    def test_generate_location_business_recommendations(self):
        from business_intelligence.analysis import generate_location_business_recommendations, generate_fallback_spatial_pois
        fallback = generate_fallback_spatial_pois(self.lat, self.lon, self.radius)
        recs = generate_location_business_recommendations(
            self.lat, self.lon, radius_m=self.radius,
            location_name=self.location_name, elements=fallback.get('elements')
        )
        self.assertEqual(len(recs), 5, "Should generate exactly top 5 recommendations")
        for idx, rec in enumerate(recs):
            self.assertEqual(rec['rank'], idx + 1)
            self.assertIn('name', rec)
            self.assertIn('category', rec)
            self.assertIn('starting_monthly_revenue', rec)
            self.assertIn('estimated_monthly_costs', rec)
            self.assertIn('estimated_monthly_profit', rec)
            self.assertGreater(rec['starting_monthly_revenue'], 0)
            self.assertGreater(rec['estimated_monthly_profit'], 0)
            self.assertIn('target_lat', rec)
            self.assertIn('target_lon', rec)
            self.assertTrue(len(rec.get('reasons', [])) >= 2, "Should provide local rationale reasons")

    def test_overpass_grid_caching(self):
        from django.core.cache import cache
        from business_intelligence.analysis import _run_overpass_query
        grid_lat = round(float(self.lat), 3)
        grid_lon = round(float(self.lon), 3)
        cache_key = f"overpass_grid_{grid_lat}_{grid_lon}_{self.radius}"

        mock_payload = {
            'is_live': True,
            'data_source': 'Verified live OpenStreetMap',
            'elements': [{'type': 'node', 'id': 101, 'lat': self.lat, 'lon': self.lon, 'tags': {'amenity': 'cafe'}}]
        }
        cache.set(cache_key, mock_payload, timeout=60)

        result, err = _run_overpass_query("test_query", timeout=1, lat=self.lat, lon=self.lon, radius=self.radius)
        self.assertIsNone(err)
        self.assertEqual(result, mock_payload)
        self.assertEqual(len(result['elements']), 1)
        cache.delete(cache_key)

    def test_find_popular_places_api_endpoint(self):
        import json
        from django.test import Client
        client = Client()
        response = client.post(
            '/find-popular-places/',
            data=json.dumps({'latitude': self.lat, 'longitude': self.lon, 'location_name': self.location_name}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('analysis_radius'), 5000)
        self.assertIn('active_sensors_count', data)
        self.assertIn('total_area_revenue', data)
        self.assertIn('recommendations', data)
        self.assertEqual(len(data['recommendations']), 5)
        self.assertIn('is_live', data)
        self.assertIn('data_source', data)

    def test_get_location_recommendations_endpoint_get(self):
        from django.test import Client
        client = Client()
        url = f"/api/location-recommendations/?latitude={self.lat}&longitude={self.lon}&location_name=MG%20Road&radius=5000"
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('analysis_radius'), 5000)
        self.assertEqual(len(data.get('recommendations', [])), 5)

    def test_get_location_recommendations_endpoint_post(self):
        import json
        from django.test import Client
        client = Client()
        response = client.post(
            '/api/location-recommendations/',
            data=json.dumps({'latitude': self.lat, 'longitude': self.lon, 'location_name': self.location_name}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(len(data.get('recommendations', [])), 5)

    def test_location_recommendations_invalid_coordinates(self):
        from django.test import Client
        client = Client()
        response = client.get('/api/location-recommendations/?latitude=invalid&longitude=77.5946')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data.get('success'))
        self.assertIn('error', data)

