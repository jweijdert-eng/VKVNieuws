"""App-URLs — Blog."""

from django.urls import path

from vkvnieuws import views

app_name = "vkvnieuws"

urlpatterns = [
    path("", views.lijst, name="index"),
    path("nieuw/", views.schrijven, name="nieuw"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/bewerken/", views.schrijven, name="bewerken"),
    path("<int:pk>/verzenden/", views.verzenden, name="verzenden"),
    path("<int:pk>/verwijderen/", views.verwijderen, name="verwijderen"),
    path("koppelen/", views.koppelen, name="koppelen"),
]
