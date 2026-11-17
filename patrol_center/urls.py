"""
URL configuration for patrol_center project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django import views
from django.contrib import admin
from django.urls import path, include
from tracker.views import update_location, home, dashboard, api_vehicles, api_polygons, api_completed_patrols, api_vehicle_summary, ingest_gps

urlpatterns = [
    path('admin/', admin.site.urls),
    path('update_location/', update_location),
	path('accounts/', include('django.contrib.auth.urls')),
    path('', dashboard, name='home'),
    path('api/vehicles/', api_vehicles, name='api_vehicles'), # This is the API endpoint for fetching vehicle data as JSON
    path('api/polygons/', api_polygons, name='api_polygons'),
    path('api/completed_patrols/', api_completed_patrols, name='api_completed_patrols'),
    path('api/vehicle_summary/', api_vehicle_summary, name='api_vehicle_summary'),
    path('api/ingest_gps/', ingest_gps, name='ingest_gps'),
]
