from django.urls import path

from api import views

urlpatterns = [
    path("health", views.health, name="health"),
    path("places", views.PlacesView.as_view(), name="places"),
    path("routes", views.RoutesView.as_view(), name="routes"),
    path("risk", views.RiskView.as_view(), name="risk"),
]
