from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('chat/', views.chat_message, name='chat_message'),
    path('search-location/', views.search_location, name='search_location'),
    path('find-popular-places/', views.find_popular_places, name='find_popular_places'),
    path('analyze-crowd-intensity/', views.analyze_crowd_intensity, name='analyze_crowd_intensity'),
    path('autocomplete-location/', views.autocomplete_location, name='autocomplete_location'),
    path('contact/', views.contact_us, name='contact_us'),
    path('api/user-location/', views.report_user_location, name='report_user_location'),
    path('api/location-recommendations/', views.get_location_recommendations, name='tracker_location_recommendations'),
]
