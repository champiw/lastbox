from datetime import date, timedelta
from django.utils import timezone
from django.db import transaction
from inventory.models import TrackedSupply, SupplyType, InsulinBox


USAGE_INTERVAL_MAP = {
    SupplyType.PUMP_SITES: 3,
    SupplyType.CGMS: 15,
}


def init_supplies(user):
    """
    Create or ensure existence of TrackedSupply records for all known supply
    types for the given user.

    Safe to call multiple times. Returns the number of records created.
    """
    created_count = 0
    for supply_type, interval in USAGE_INTERVAL_MAP.items():
        _, created = TrackedSupply.objects.get_or_create(
            user=user,
            supply_type=supply_type,
            defaults={'usage_interval_days': interval},
        )
        if created:
            created_count += 1
    return created_count


@transaction.atomic
def remove_stock(user, supply_type):
    """
    Remove a unit of a supply: decrement quantity by 1 and set last_used_at to today.

    Raises ValueError if quantity is 0 or supply_type is unknown for the user.
    """
    try:
        supply = TrackedSupply.objects.get(user=user, supply_type=supply_type)
    except TrackedSupply.DoesNotExist:
        raise ValueError(f"Unknown supply type: {supply_type}")

    if supply.quantity <= 0:
        raise ValueError(f"Cannot remove stock: {supply_type} has no stock remaining")

    supply.quantity -= 1
    supply.last_used_at = timezone.localdate()
    supply.save()


@transaction.atomic
def add_stock(user, supply_type, count):
    """
    Add a count to the existing quantity of a supply.

    Raises ValueError if count is less than 0 or supply_type is unknown for the user.
    """
    if count < 0:
        raise ValueError(f"Cannot add negative stock: {count}")

    try:
        supply = TrackedSupply.objects.get(user=user, supply_type=supply_type)
    except TrackedSupply.DoesNotExist:
        raise ValueError(f"Unknown supply type: {supply_type}")

    supply.quantity += count
    supply.save()


@transaction.atomic
def edit_stock(user, supply_type, quantity):
    """
    Set the quantity of a supply to an explicit value.

    Raises ValueError if quantity is negative or supply_type is unknown for the user.
    """
    if quantity < 0:
        raise ValueError(f"Quantity cannot be negative: {quantity}")

    try:
        supply = TrackedSupply.objects.get(user=user, supply_type=supply_type)
    except TrackedSupply.DoesNotExist:
        raise ValueError(f"Unknown supply type: {supply_type}")

    supply.quantity = quantity
    supply.save()


def calculate_estimated_change_dates(user, supply_type):
    """
    Calculate estimated future change dates for a supply belonging to the user.

    Returns a sorted list of date objects, one per remaining item in stock.
    Each date is calculated from last_used_at plus multiples of usage_interval_days.
    If last_used_at is not set or quantity is zero, returns an empty list.
    Does not modify the database.

    Raises ValueError if supply_type is unknown for the user.
    """
    try:
        supply = TrackedSupply.objects.get(user=user, supply_type=supply_type)
    except TrackedSupply.DoesNotExist:
        raise ValueError(f"Unknown supply type: {supply_type}")

    if not supply.last_used_at or supply.quantity <= 0:
        return []

    dates = []
    for i in range(1, supply.quantity + 1):
        estimated_date = supply.last_used_at + timedelta(days=supply.usage_interval_days * i)
        dates.append(estimated_date)

    return sorted(dates)


@transaction.atomic
def add_insulin_box(user, expiration_date):
    """
    Add one unopened insulin box owned by the user with the given expiration date.

    vials_remaining is initialized to 5.

    Raises ValueError if expiration_date is None or in the past.
    Returns the created InsulinBox instance.
    """
    if expiration_date is None:
        raise ValueError("Expiration date is required")

    if isinstance(expiration_date, str):
        try:
            expiration_date = date.fromisoformat(expiration_date)
        except ValueError:
            raise ValueError(f"Invalid expiration date format: {expiration_date}")

    today = timezone.localdate()
    if expiration_date < today:
        raise ValueError(
            f"Expiration date cannot be in the past: {expiration_date}"
        )

    box = InsulinBox.objects.create(
        user=user,
        expiration_date=expiration_date,
        vials_remaining=5,
    )
    return box


def get_soonest_expiring_boxes(user):
    """
    Return at most two of the user's insulin boxes, ordered by earliest
    expiration_date first.

    Ties are broken by primary key (ascending).
    Returns fewer than two boxes when fewer exist.
    Does not filter out expired boxes.
    """
    return list(
        InsulinBox.objects.filter(user=user).order_by('expiration_date', 'pk')[:2]
    )


@transaction.atomic
def deduct_vial_from_box(user, box_id):
    """
    Deduct exactly one vial from the specified box owned by the user.

    The caller must identify which box to use.
    Raises ValueError if the box does not exist for this user or has no
    remaining vials.
    If the box reaches zero vials, its record is deleted immediately.
    """
    try:
        box = InsulinBox.objects.get(pk=box_id, user=user)
    except InsulinBox.DoesNotExist:
        raise ValueError(f"Insulin box with id {box_id} does not exist")

    if box.vials_remaining <= 0:
        raise ValueError(
            f"Insulin box with id {box_id} has no vials remaining"
        )

    if box.vials_remaining == 1:
        box.delete()
    else:
        box.vials_remaining -= 1
        box.save()
