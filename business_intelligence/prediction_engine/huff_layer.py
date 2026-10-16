"""
Dynamic Huff Model Layer.
Implements distance decay, customer choice probability, store attractiveness,
and market share using GIS spatial nodes as customer demand origins.
"""

import math
from typing import List, Dict, Tuple, Any
from .config import (
    DEFAULT_HUFF_LAMBDA,
    BUSINESS_METRICS,
    TEMPORAL_PATTERNS
)
from .data_classes import HuffMetrics

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in meters."""
    radius = 6371000.0  # Earth's radius in meters
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2.0) ** 2 +
         math.cos(p1) * math.cos(p2) * math.sin(dlon / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return radius * c

def is_competitor(poi_type: str, business_type: str) -> bool:
    """Same-category rule shared by the Huff layers (and the PDF report's competitor list)."""
    if business_type == 'default' or not poi_type:
        return False
    return poi_type == business_type or business_type in poi_type or poi_type in business_type


class HuffModel:
    """Computes customer attraction, choice probability, and trading area market share."""

    def __init__(self, target_lat: float, target_lon: float, business_type: str):
        self.target_lat = target_lat
        self.target_lon = target_lon
        self.business_type = business_type.strip().lower().replace(' ', '_')
        
        # Load business metrics for decay lambda and base attractiveness
        metrics = BUSINESS_METRICS.get(self.business_type, BUSINESS_METRICS['default'])
        self.lambda_decay = DEFAULT_HUFF_LAMBDA
        # If sensitivity is high, increase distance decay (people won't travel as far)
        if metrics['sensitivity'] == 'high':
            self.lambda_decay = 2.0
        elif metrics['sensitivity'] == 'low':
            self.lambda_decay = 1.1
            
        self.base_attractiveness = metrics.get('attractiveness_base', 1.0)

    def _extract_competitors(self, elements: List[Dict[str, Any]]) -> List[Tuple[float, float]]:
        """Extract coordinate tuples of competitor businesses."""
        competitors = []
        for el in elements:
            # Competitors were identified in the feature extractor. We re-identify here.
            tags = el.get('tags') or {}
            amenity = tags.get('amenity', '')
            shop = tags.get('shop', '')
            tourism = tags.get('tourism', '')
            
            poi_type = (amenity or shop or tourism or '').lower().replace(' ', '_')
            if not poi_type:
                continue
                
            if is_competitor(poi_type, self.business_type):
                lat = el.get('lat') or (el.get('center') or {}).get('lat')
                lon = el.get('lon') or (el.get('center') or {}).get('lon')
                if lat is not None and lon is not None:
                    dist = haversine(self.target_lat, self.target_lon, float(lat), float(lon))
                    if dist > 10.0:  # Exclude the target store itself
                        competitors.append((float(lat), float(lon)))
        return competitors

    def _generate_demand_origins(self, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract customer demand nodes (residential/offices) or synthesize a fallback grid."""
        origins = []
        
        for el in elements:
            tags = el.get('tags') or {}
            building = tags.get('building', '')
            office = tags.get('office', '')
            lat = el.get('lat') or (el.get('center') or {}).get('lat')
            lon = el.get('lon') or (el.get('center') or {}).get('lon')
            
            if lat is None or lon is None:
                continue
                
            demand_weight = 0.0
            if building in ('residential', 'apartments', 'house', 'terrace', 'detached', 'dormitory'):
                demand_weight = 15.0
            elif office or building == 'office':
                demand_weight = 20.0
            elif building in ('commercial', 'retail'):
                demand_weight = 10.0
                
            if demand_weight > 0:
                origins.append({
                    'lat': float(lat),
                    'lon': float(lon),
                    'weight': demand_weight
                })

        # Synthesize fallback grid if no demand nodes were found in the vicinity
        if not origins:
            # Generate 9-point grid (center + 8 compass headings at 300m and 800m offsets)
            offsets_deg = [
                (0.0, 0.0),                      # Center
                (0.003, 0.0), (0.0, 0.003),      # Close N, E
                (-0.003, 0.0), (0.0, -0.003),    # Close S, W
                (0.007, 0.007), (-0.007, -0.007),# Far NE, SW
                (0.007, -0.007), (-0.007, 0.007) # Far NW, SE
            ]
            for i, (dlat, dlon) in enumerate(offsets_deg):
                origins.append({
                    'lat': self.target_lat + dlat,
                    'lon': self.target_lon + dlon,
                    'weight': 10.0 if i == 0 else 5.0
                })
                
        return origins

    def compute_huff_metrics(
        self,
        elements: List[Dict[str, Any]],
        accessibility_score: float,
        business_attraction_score: float,
        area_diversity_score: float,
        income_proxy: float,
        expected_visitors: float
    ) -> HuffMetrics:
        """Computes Huff gravity model parameters for the target site."""
        # 1. Target store attractiveness (A_target)
        # Higher accessibility, attraction, diversity, and customer spending power boost attractiveness
        store_attraction = (
            self.base_attractiveness *
            (1.0 + accessibility_score / 100.0) *
            (1.0 + business_attraction_score / 100.0) *
            (1.0 + area_diversity_score / 100.0) *
            (1.0 + income_proxy / 100.0)
        )
        
        # 2. Extract competitor nodes
        competitors = self._extract_competitors(elements)
        
        # Competitor attractiveness (A_comp)
        # Using a standard baseline modified slightly by local diversity to represent competition strength
        competitor_attraction = self.base_attractiveness * (1.0 + area_diversity_score / 150.0)
        
        # 3. Load demand origins
        origins = self._generate_demand_origins(elements)
        
        # 4. Run Huff Probability calculation over all origin points
        total_weighted_probability = 0.0
        total_demand_weight = 0.0
        
        # Track average distance decay factor
        total_distance_decay = 0.0
        
        for origin in origins:
            o_lat, o_lon = origin['lat'], origin['lon']
            o_weight = origin['weight']
            
            # Distance to target (min 10 meters to avoid division by zero / extreme gravity)
            d_target = max(10.0, haversine(o_lat, o_lon, self.target_lat, self.target_lon))
            
            # Target store utility
            utility_target = store_attraction / (d_target ** self.lambda_decay)
            
            # Competitors utility sum
            utility_competitors_sum = 0.0
            for c_lat, c_lon in competitors:
                d_c = max(10.0, haversine(o_lat, o_lon, c_lat, c_lon))
                utility_competitors_sum += competitor_attraction / (d_c ** self.lambda_decay)
                
            # Choice Probability (P_i)
            total_utility = utility_target + utility_competitors_sum
            prob_target = utility_target / total_utility if total_utility > 0.0 else 1.0
            
            total_weighted_probability += prob_target * o_weight
            total_demand_weight += o_weight
            
            # Distance decay contribution
            total_distance_decay += (1.0 / (d_target ** self.lambda_decay)) * o_weight

        # Market Share (Weighted Choice Probability)
        market_share = total_weighted_probability / total_demand_weight if total_demand_weight > 0 else 1.0
        avg_distance_decay = total_distance_decay / total_demand_weight if total_demand_weight > 0 else 0.01

        # 5. Compute Time-aware customer visits
        # We model dynamic customer hourly visits using diurnal patterns
        time_aware_visits = {}
        for hour, (mult, _) in TEMPORAL_PATTERNS.items():
            # Visits fluctuate based on temporal volume, market share, and expected visitors
            visits = expected_visitors * mult * market_share
            time_aware_visits[hour] = round(visits, 2)

        return HuffMetrics(
            choice_probability=round(market_share, 4),  # Choice probability at trading area scale
            distance_decay=round(avg_distance_decay, 6),
            store_attraction=round(store_attraction, 2),
            market_share=round(market_share, 4),
            time_aware_visits=time_aware_visits
        )
