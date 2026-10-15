from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from inventory.models import TrackedSupply, SupplyType
from inventory.services import (
    calculate_estimated_change_dates,
    get_soonest_expiring_boxes,
)


@login_required
def dashboard(request):
    tracked = {
        supply.supply_type: supply
        for supply in TrackedSupply.objects.filter(user=request.user)
    }

    supplies = []
    for supply_type in SupplyType:
        supply = tracked.get(supply_type.value)
        supplies.append({
            'supply_type': supply_type,
            'supply': supply,
            'change_dates': (
                calculate_estimated_change_dates(request.user, supply_type.value)
                if supply else []
            ),
        })

    return render(request, 'inventory/dashboard.html', {
        'supplies': supplies,
        'boxes': get_soonest_expiring_boxes(request.user),
    })
