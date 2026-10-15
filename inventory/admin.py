from django.contrib import admin

from .models import InsulinBox, TrackedSupply


@admin.register(InsulinBox)
class InsulinBoxAdmin(admin.ModelAdmin):
    list_display = ('user', 'expiration_date', 'vials_remaining', 'created_at')
    list_filter = ('user', 'expiration_date')
    search_fields = ('expiration_date',)


@admin.register(TrackedSupply)
class TrackedSupplyAdmin(admin.ModelAdmin):
    list_display = ('user', 'supply_type', 'quantity', 'usage_interval_days', 'last_used_at')
    list_filter = ('user', 'supply_type')
