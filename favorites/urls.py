from django.urls import path

from . import views

urlpatterns = [
    path('favorites/', views.favorites_page, name='favorites'),
    path('api/favorites/', views.favorites_collection, name='favorites_collection'),
    path('api/favorites/toggle/', views.favorite_toggle, name='favorite_toggle'),
    path('api/favorites/recommendations/', views.recommendations, name='favorite_recommendations'),
    path('api/favorites/<int:pk>/', views.favorite_detail, name='favorite_detail'),
]
