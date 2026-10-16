from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from inventory.models import TrackedSupply, SupplyType
from inventory.services import (
    add_insulin_box,
    add_stock,
    calculate_estimated_change_dates,
    deduct_vial_from_box,
    get_soonest_expiring_boxes,
    remove_stock,
)


def _require_known_supply_type(supply_type):
    if supply_type not in SupplyType.values:
        raise Http404(f"Unknown supply type: {supply_type}")


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


@login_required
def add_supplies(request):
    return render(request, 'inventory/add.html', {
        'today': timezone.localdate().isoformat(),
    })


@login_required
@require_POST
def use_supply(request, supply_type):
    _require_known_supply_type(supply_type)
    label = SupplyType(supply_type).label
    try:
        remove_stock(request.user, supply_type)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Logged use of {label}.")
    return redirect('dashboard')


@login_required
@require_POST
def add_supply(request, supply_type):
    _require_known_supply_type(supply_type)
    label = SupplyType(supply_type).label
    try:
        count = int(request.POST.get('count'))
    except (TypeError, ValueError):
        messages.error(request, "Enter a whole number.")
        return redirect('add_supplies')

    try:
        add_stock(request.user, supply_type, count)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Added {count} {label}.")
    return redirect('add_supplies')


@login_required
@require_POST
def add_box(request):
    expiration_date = request.POST.get('expiration_date')
    try:
        box = add_insulin_box(request.user, expiration_date)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request, f"Added insulin box expiring {box.expiration_date}."
        )
    return redirect('add_supplies')


@login_required
@require_POST
def use_vial(request, box_id):
    try:
        deduct_vial_from_box(request.user, box_id)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Removed one vial.")
    return redirect('dashboard')
