from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('profile/', views.profile_view, name='profile'),
    path('submit-form/', views.submit_form, name='submit_form'),
    path('check-feasibility/', views.check_feasibility, name='check_feasibility'),
    path('business-recommendations/', views.business_recommendations, name='business_recommendations'),
    path('api/analyze-location/', views.analyze_location, name='analyze_location'),
    path('api/generate-best-locations/', views.generate_best_locations, name='generate_best_locations'),
    path('api/business-types/', views.get_business_types, name='get_business_types'),
    path('api/find-matching-locations/', views.find_matching_locations, name='find_matching_locations'),
    path('api/location-recommendations/', views.get_location_recommendations, name='get_location_recommendations'),
    path('api/log-activity/', views.log_activity_api, name='log_activity_api'),
]
