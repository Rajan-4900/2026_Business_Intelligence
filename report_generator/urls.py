from django.urls import path

from . import views

urlpatterns = [
    path('api/reports/', views.list_reports, name='report_list'),
    path('api/reports/generate/', views.generate_report, name='report_generate'),
    path('api/reports/<uuid:report_id>/status/', views.report_status, name='report_status'),
    path('api/reports/<uuid:report_id>/download/', views.download_report, name='report_download'),
]
