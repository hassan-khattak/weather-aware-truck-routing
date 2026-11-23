from django.urls import path

from api import views

urlpatterns = [
    path("health", views.health, name="health"),
    path("places", views.PlacesView.as_view(), name="places"),
]
