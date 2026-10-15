from django.urls import path

from inventory import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
]
