from django.urls import path

from inventory import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('add/', views.add_supplies, name='add_supplies'),
    path('supplies/<str:supply_type>/use/', views.use_supply, name='use_supply'),
    path('supplies/<str:supply_type>/add/', views.add_supply, name='add_supply'),
    path('boxes/add/', views.add_box, name='add_box'),
    path('boxes/<int:box_id>/use-vial/', views.use_vial, name='use_vial'),
]
