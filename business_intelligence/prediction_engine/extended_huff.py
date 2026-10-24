"""
Extended Huff Model Layer.
Implements competition adjustments, demand-supply balance, store performance
benchmarking, and revenue confidence calculations.
"""

import math
from typing import List, Dict, Any
from .config import (
    DEFAULT_EXTENDED_GAMMA,
    DEFAULT_EXTENDED_EPSILON,
    BUSINESS_METRICS
)
from .data_classes import ExtendedHuffMetrics
from .huff_layer import is_competitor

class ExtendedHuffModel:
    """Implements benchmarking adjustments and corrections for retail network performance."""

    def __init__(self, business_type: str):
        self.business_type = business_type.strip().lower().replace(' ', '_')
        self.gamma = DEFAULT_EXTENDED_GAMMA
        self.metrics = BUSINESS_METRICS.get(self.business_type, BUSINESS_METRICS['default'])

    def _get_competitor_count(self, elements: List[Dict[str, Any]]) -> int:
        """Count competitors of the same business type."""
        count = 0
        for el in elements:
            tags = el.get('tags') or {}
            poi_type = (tags.get('amenity') or tags.get('shop') or tags.get('tourism') or '').lower().replace(' ', '_')
            if not poi_type:
                continue
                
            if is_competitor(poi_type, self.business_type):
                count += 1
        return count

    def compute_extended_metrics(
        self,
        elements: List[Dict[str, Any]],
        market_share: float,
        expected_visitors: float,
        accessibility_score: float,
        competition_score: float,
        demand_supply_ratio: float
    ) -> ExtendedHuffMetrics:
        """Calculates extended Huff model parameters including adjustments and confidence ratings."""
        # 1. Competition Adjustment
        # Models how additional same-type stores discount market capture (Paper 2)
        competitor_count = self._get_competitor_count(elements)
        # Exclude the hypothetical target itself if counted
        comp_count_adjusted = max(0, competitor_count - 1)
        competition_adjustment = math.exp(-self.gamma * comp_count_adjusted)
        
        # Adjusted Expected customer flow
        # Projected daily customers visiting our store
        opt_min, opt_max = self.metrics['optimal_range']
        conversion_rate = self.metrics['base_conv']
        
        daily_visits = expected_visitors * market_share * competition_adjustment
        daily_customers = daily_visits * conversion_rate
        
        # 2. Business/Store Performance Benchmarking
        # Evaluate how close estimated customers are to the store's capacity limits
        # Too many customers = crowding penalty (lost business), too few = under-performance
        if opt_min <= daily_customers <= opt_max:
            business_performance = 1.0  # Perfect alignment
        elif daily_customers > opt_max:
            # Overcapacity penalty
            excess_ratio = (daily_customers - opt_max) / opt_max
            penalty_severity = 0.5 if self.metrics['sensitivity'] == 'high' else 0.2
            business_performance = max(0.4, 1.0 - (excess_ratio * penalty_severity))
        else:
            # Undercapacity discount
            shortfall_ratio = (opt_min - daily_customers) / opt_min
            business_performance = max(0.3, 1.0 - (shortfall_ratio * 0.4))

        # 3. Retail Turnover Prediction (Daily Revenue)
        avg_spend = self.metrics['avg_spend']
        retail_turnover = daily_customers * avg_spend * business_performance

        # 4. Revenue Confidence Score
        # Based on POI density, spatial alignment, and competitor variability.
        # Volatility rises with extreme competition or low data density.
        poi_count = len(elements)
        data_density_score = min(40.0, (poi_count / 80.0) * 40.0)
        accessibility_bonus = (accessibility_score / 100.0) * 15.0
        
        # High competition reduces confidence slightly due to high market variance
        competition_penalty = (competition_score / 100.0) * 10.0
        
        raw_confidence = 45.0 + data_density_score + accessibility_bonus - competition_penalty
        revenue_confidence = min(95.0, max(15.0, raw_confidence))

        return ExtendedHuffMetrics(
            competition_adjustment=round(competition_adjustment, 4),
            demand_supply_ratio=round(demand_supply_ratio, 3),
            business_performance=round(business_performance, 3),
            retail_turnover=round(retail_turnover, 2),
            revenue_confidence=round(revenue_confidence, 1)
        )
