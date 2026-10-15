from datetime import date, timedelta
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from django.db.models import Sum
from inventory.models import InsulinBox, TrackedSupply, SupplyType
from inventory.services import (
    add_insulin_box,
    get_soonest_expiring_boxes,
    deduct_vial_from_box,
    remove_stock,
    add_stock,
    edit_stock,
    calculate_estimated_change_dates,
    init_supplies,
)


class TestAddInsulinBox(TestCase):
    def test_adds_box_with_correct_expiration_and_vial_count(self):
        exp_date = date.today() + timedelta(days=30)
        box = add_insulin_box(exp_date)
        self.assertEqual(box.expiration_date, exp_date)
        self.assertEqual(box.vials_remaining, 5)

    def test_adds_box_with_future_date(self):
        exp_date = date.today() + timedelta(days=365)
        box = add_insulin_box(exp_date)
        self.assertEqual(box.expiration_date, exp_date)
        self.assertEqual(box.vials_remaining, 5)

    def test_adds_box_with_today_as_expiration(self):
        box = add_insulin_box(date.today())
        self.assertEqual(box.expiration_date, date.today())
        self.assertEqual(box.vials_remaining, 5)

    def test_adds_box_with_string_date(self):
        exp_date = date.today() + timedelta(days=30)
        box = add_insulin_box(exp_date.isoformat())
        self.assertEqual(box.expiration_date, exp_date)

    def test_rejects_none_expiration_date(self):
        with self.assertRaises(ValueError):
            add_insulin_box(None)

    def test_rejects_past_expiration_date(self):
        past_date = date.today() - timedelta(days=1)
        with self.assertRaises(ValueError):
            add_insulin_box(past_date)

    def test_rejects_very_past_expiration_date(self):
        past_date = date(2020, 1, 1)
        with self.assertRaises(ValueError):
            add_insulin_box(past_date)

    def test_rejects_invalid_string_format(self):
        with self.assertRaises(ValueError):
            add_insulin_box("not-a-date")

    def test_rejects_partial_string_format(self):
        with self.assertRaises(ValueError):
            add_insulin_box("2025-12")

    def test_creates_separate_records_per_call(self):
        exp_date = date.today() + timedelta(days=30)
        box1 = add_insulin_box(exp_date)
        box2 = add_insulin_box(exp_date)
        self.assertNotEqual(box1.pk, box2.pk)
        self.assertEqual(InsulinBox.objects.count(), 2)


class TestGetSoonestExpiringBoxes(TestCase):
    def test_returns_two_boxes_when_available(self):
        add_insulin_box(date.today() + timedelta(days=10))
        add_insulin_box(date.today() + timedelta(days=20))
        boxes = get_soonest_expiring_boxes()
        self.assertEqual(len(boxes), 2)

    def test_returns_one_box_when_only_one_exists(self):
        add_insulin_box(date.today() + timedelta(days=30))
        boxes = get_soonest_expiring_boxes()
        self.assertEqual(len(boxes), 1)

    def test_returns_empty_list_when_no_boxes_exist(self):
        boxes = get_soonest_expiring_boxes()
        self.assertEqual(len(boxes), 0)

    def test_orders_by_earliest_expiration_first(self):
        box_later = add_insulin_box(date.today() + timedelta(days=60))
        box_earlier = add_insulin_box(date.today() + timedelta(days=10))
        boxes = get_soonest_expiring_boxes()
        self.assertEqual(boxes[0].pk, box_earlier.pk)
        self.assertEqual(boxes[1].pk, box_later.pk)

    def test_returns_fewer_than_two_when_three_exist(self):
        add_insulin_box(date.today() + timedelta(days=10))
        add_insulin_box(date.today() + timedelta(days=20))
        add_insulin_box(date.today() + timedelta(days=30))
        boxes = get_soonest_expiring_boxes()
        self.assertEqual(len(boxes), 2)

    def test_breaks_ties_by_primary_key(self):
        box_a = add_insulin_box(date.today() + timedelta(days=30))
        box_b = add_insulin_box(date.today() + timedelta(days=30))
        boxes = get_soonest_expiring_boxes()
        self.assertEqual(boxes[0].pk, box_a.pk)
        self.assertEqual(boxes[1].pk, box_b.pk)

    def test_includes_expired_boxes(self):
        InsulinBox.objects.create(
            expiration_date=date.today() - timedelta(days=10),
            vials_remaining=3,
        )
        add_insulin_box(date.today() + timedelta(days=10))
        boxes = get_soonest_expiring_boxes()
        self.assertEqual(len(boxes), 2)
        self.assertTrue(
            any(b.expiration_date < date.today() for b in boxes)
        )


class TestDeductVialFromBox(TestCase):
    def test_deducts_one_vial(self):
        box = add_insulin_box(date.today() + timedelta(days=30))
        deduct_vial_from_box(box.pk)
        box.refresh_from_db()
        self.assertEqual(box.vials_remaining, 4)

    def test_deducts_from_specific_box_only(self):
        box_a = add_insulin_box(date.today() + timedelta(days=10))
        box_b = add_insulin_box(date.today() + timedelta(days=20))
        deduct_vial_from_box(box_a.pk)
        box_a.refresh_from_db()
        box_b.refresh_from_db()
        self.assertEqual(box_a.vials_remaining, 4)
        self.assertEqual(box_b.vials_remaining, 5)

    def test_deletes_box_after_fifth_vial_used(self):
        box = add_insulin_box(date.today() + timedelta(days=30))
        for _ in range(5):
            deduct_vial_from_box(box.pk)
        with self.assertRaises(InsulinBox.DoesNotExist):
            InsulinBox.objects.get(pk=box.pk)
        self.assertEqual(InsulinBox.objects.count(), 0)

    def test_rejects_nonexistent_box(self):
        with self.assertRaises(ValueError) as ctx:
            deduct_vial_from_box(99999)
        self.assertIn("does not exist", str(ctx.exception))

    def test_rejects_depleted_box(self):
        box = add_insulin_box(date.today() + timedelta(days=30))
        for _ in range(5):
            deduct_vial_from_box(box.pk)
        with self.assertRaises(ValueError):
            deduct_vial_from_box(box.pk)

    def test_tracks_correct_remaining_after_multiple_deductions(self):
        box = add_insulin_box(date.today() + timedelta(days=30))
        deduct_vial_from_box(box.pk)
        deduct_vial_from_box(box.pk)
        deduct_vial_from_box(box.pk)
        box.refresh_from_db()
        self.assertEqual(box.vials_remaining, 2)


class TestConcurrentVialDeduction(TransactionTestCase):
    def test_concurrent_deduction_handles_contention(self):
        from django.db import OperationalError
        box = add_insulin_box(date.today() + timedelta(days=30))

        results = []

        def worker():
            try:
                for _ in range(5):
                    deduct_vial_from_box(box.pk)
                results.append('ok')
            except (ValueError, OperationalError):
                results.append('rejected')

        import threading
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify contention handling: some operations should have been rejected
        # or at most the same number of boxes exist as we started with
        self.assertIn('rejected', results)
        total_remaining = InsulinBox.objects.filter(
            expiration_date=box.expiration_date
        ).aggregate(total=Sum('vials_remaining'))['total']
        self.assertLessEqual(total_remaining or 0, 5)


class TestConcurrentStockRemoval(TransactionTestCase):
    def test_concurrent_remove_stock_handles_contention(self):
        from django.db import OperationalError
        init_supplies()
        supply = TrackedSupply.objects.get(supply_type=SupplyType.PUMP_SITES)
        original_qty = supply.quantity

        results = []

        def worker():
            try:
                for _ in range(original_qty):
                    remove_stock(SupplyType.PUMP_SITES)
                results.append('ok')
            except (ValueError, OperationalError):
                results.append('rejected')

        import threading
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        supply.refresh_from_db()
        self.assertEqual(supply.quantity, 0)
        self.assertIn('ok', results)


class TestRemoveStockDate(TestCase):
    def test_sets_last_used_at_on_removal(self):
        init_supplies()
        add_stock(SupplyType.PUMP_SITES, 5)
        before = timezone.localdate() - timedelta(days=1)
        supply = TrackedSupply.objects.get(supply_type=SupplyType.PUMP_SITES)
        supply.last_used_at = before
        supply.save()

        remove_stock(SupplyType.PUMP_SITES)
        supply.refresh_from_db()
        self.assertGreater(supply.last_used_at, before)

    def test_updates_last_used_at_on_each_removal(self):
        init_supplies()
        add_stock(SupplyType.PUMP_SITES, 5)
        supply = TrackedSupply.objects.get(supply_type=SupplyType.PUMP_SITES)
        supply.last_used_at = date(2020, 1, 1)
        supply.save()

        remove_stock(SupplyType.PUMP_SITES)
        remove_stock(SupplyType.PUMP_SITES)
        supply.refresh_from_db()
        self.assertEqual(supply.last_used_at, timezone.localdate())


class TestCalculateEstimatedChangeDates(TestCase):
    def test_returns_date_objects(self):
        init_supplies()
        supply = TrackedSupply.objects.get(supply_type=SupplyType.PUMP_SITES)
        supply.last_used_at = date(2025, 1, 1)
        supply.save()

        dates = calculate_estimated_change_dates(SupplyType.PUMP_SITES)
        self.assertTrue(all(isinstance(d, date) and not hasattr(d, 'hour') for d in dates))

    def test_returns_empty_list_when_no_last_used_at(self):
        init_supplies()
        supply = TrackedSupply.objects.get(supply_type=SupplyType.PUMP_SITES)
        supply.last_used_at = None
        supply.save()

        dates = calculate_estimated_change_dates(SupplyType.PUMP_SITES)
        self.assertEqual(dates, [])

    def test_returns_empty_list_when_quantity_is_zero(self):
        init_supplies()
        supply = TrackedSupply.objects.get(supply_type=SupplyType.PUMP_SITES)
        supply.last_used_at = date(2025, 1, 1)
        supply.quantity = 0
        supply.save()

        dates = calculate_estimated_change_dates(SupplyType.PUMP_SITES)
        self.assertEqual(dates, [])

    def test_returns_correct_number_of_dates(self):
        init_supplies()
        supply = TrackedSupply.objects.get(supply_type=SupplyType.PUMP_SITES)
        supply.last_used_at = date(2025, 1, 1)
        supply.save()

        dates = calculate_estimated_change_dates(SupplyType.PUMP_SITES)
        self.assertEqual(len(dates), supply.quantity)

    def test_returns_sorted_dates(self):
        init_supplies()
        supply = TrackedSupply.objects.get(supply_type=SupplyType.PUMP_SITES)
        supply.last_used_at = date(2025, 1, 1)
        supply.save()

        dates = calculate_estimated_change_dates(SupplyType.PUMP_SITES)
        self.assertEqual(dates, sorted(dates))

    def test_raises_value_error_for_unknown_supply_type(self):
        with self.assertRaises(ValueError):
            calculate_estimated_change_dates("NONEXISTENT")


class TestAddInsulinBoxDateParsing(TestCase):
    def test_parses_isoformat_date_string(self):
        exp_date = date(2026, 12, 15)
        box = add_insulin_box(exp_date.isoformat())
        self.assertEqual(box.expiration_date, exp_date)

    def test_rejects_date_with_spaces(self):
        with self.assertRaises(ValueError):
            add_insulin_box("2026-12-15 ")

    def test_rejects_slash_separator(self):
        with self.assertRaises(ValueError):
            add_insulin_box("2026/12/15")

    def test_accepts_date_object_directly(self):
        exp_date = date(2027, 6, 1)
        box = add_insulin_box(exp_date)
        self.assertEqual(box.expiration_date, exp_date)

    def test_rejects_negative_year_string(self):
        with self.assertRaises(ValueError):
            add_insulin_box("-0001-01-01")