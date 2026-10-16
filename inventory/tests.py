from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
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


User = get_user_model()


class UserTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='pw')


class TestAddInsulinBox(UserTestCase):
    def test_adds_box_with_correct_expiration_and_vial_count(self):
        exp_date = date.today() + timedelta(days=30)
        box = add_insulin_box(self.user, exp_date)
        self.assertEqual(box.expiration_date, exp_date)
        self.assertEqual(box.vials_remaining, 5)

    def test_adds_box_with_future_date(self):
        exp_date = date.today() + timedelta(days=365)
        box = add_insulin_box(self.user, exp_date)
        self.assertEqual(box.expiration_date, exp_date)
        self.assertEqual(box.vials_remaining, 5)

    def test_adds_box_with_today_as_expiration(self):
        box = add_insulin_box(self.user, date.today())
        self.assertEqual(box.expiration_date, date.today())
        self.assertEqual(box.vials_remaining, 5)

    def test_adds_box_with_string_date(self):
        exp_date = date.today() + timedelta(days=30)
        box = add_insulin_box(self.user, exp_date.isoformat())
        self.assertEqual(box.expiration_date, exp_date)

    def test_rejects_none_expiration_date(self):
        with self.assertRaises(ValueError):
            add_insulin_box(self.user, None)

    def test_rejects_past_expiration_date(self):
        past_date = date.today() - timedelta(days=1)
        with self.assertRaises(ValueError):
            add_insulin_box(self.user, past_date)

    def test_rejects_very_past_expiration_date(self):
        past_date = date(2020, 1, 1)
        with self.assertRaises(ValueError):
            add_insulin_box(self.user, past_date)

    def test_rejects_invalid_string_format(self):
        with self.assertRaises(ValueError):
            add_insulin_box(self.user, "not-a-date")

    def test_rejects_partial_string_format(self):
        with self.assertRaises(ValueError):
            add_insulin_box(self.user, "2025-12")

    def test_creates_separate_records_per_call(self):
        exp_date = date.today() + timedelta(days=30)
        box1 = add_insulin_box(self.user, exp_date)
        box2 = add_insulin_box(self.user, exp_date)
        self.assertNotEqual(box1.pk, box2.pk)
        self.assertEqual(InsulinBox.objects.filter(user=self.user).count(), 2)

    def test_box_belongs_to_given_user(self):
        box = add_insulin_box(self.user, date.today() + timedelta(days=30))
        self.assertEqual(box.user, self.user)


class TestGetSoonestExpiringBoxes(UserTestCase):
    def test_returns_two_boxes_when_available(self):
        add_insulin_box(self.user, date.today() + timedelta(days=10))
        add_insulin_box(self.user, date.today() + timedelta(days=20))
        boxes = get_soonest_expiring_boxes(self.user)
        self.assertEqual(len(boxes), 2)

    def test_returns_one_box_when_only_one_exists(self):
        add_insulin_box(self.user, date.today() + timedelta(days=30))
        boxes = get_soonest_expiring_boxes(self.user)
        self.assertEqual(len(boxes), 1)

    def test_returns_empty_list_when_no_boxes_exist(self):
        boxes = get_soonest_expiring_boxes(self.user)
        self.assertEqual(len(boxes), 0)

    def test_orders_by_earliest_expiration_first(self):
        box_later = add_insulin_box(self.user, date.today() + timedelta(days=60))
        box_earlier = add_insulin_box(self.user, date.today() + timedelta(days=10))
        boxes = get_soonest_expiring_boxes(self.user)
        self.assertEqual(boxes[0].pk, box_earlier.pk)
        self.assertEqual(boxes[1].pk, box_later.pk)

    def test_returns_fewer_than_two_when_three_exist(self):
        add_insulin_box(self.user, date.today() + timedelta(days=10))
        add_insulin_box(self.user, date.today() + timedelta(days=20))
        add_insulin_box(self.user, date.today() + timedelta(days=30))
        boxes = get_soonest_expiring_boxes(self.user)
        self.assertEqual(len(boxes), 2)

    def test_breaks_ties_by_primary_key(self):
        box_a = add_insulin_box(self.user, date.today() + timedelta(days=30))
        box_b = add_insulin_box(self.user, date.today() + timedelta(days=30))
        boxes = get_soonest_expiring_boxes(self.user)
        self.assertEqual(boxes[0].pk, box_a.pk)
        self.assertEqual(boxes[1].pk, box_b.pk)

    def test_includes_expired_boxes(self):
        InsulinBox.objects.create(
            user=self.user,
            expiration_date=date.today() - timedelta(days=10),
            vials_remaining=3,
        )
        add_insulin_box(self.user, date.today() + timedelta(days=10))
        boxes = get_soonest_expiring_boxes(self.user)
        self.assertEqual(len(boxes), 2)
        self.assertTrue(
            any(b.expiration_date < date.today() for b in boxes)
        )


class TestDeductVialFromBox(UserTestCase):
    def test_deducts_one_vial(self):
        box = add_insulin_box(self.user, date.today() + timedelta(days=30))
        deduct_vial_from_box(self.user, box.pk)
        box.refresh_from_db()
        self.assertEqual(box.vials_remaining, 4)

    def test_deducts_from_specific_box_only(self):
        box_a = add_insulin_box(self.user, date.today() + timedelta(days=10))
        box_b = add_insulin_box(self.user, date.today() + timedelta(days=20))
        deduct_vial_from_box(self.user, box_a.pk)
        box_a.refresh_from_db()
        box_b.refresh_from_db()
        self.assertEqual(box_a.vials_remaining, 4)
        self.assertEqual(box_b.vials_remaining, 5)

    def test_deletes_box_after_fifth_vial_used(self):
        box = add_insulin_box(self.user, date.today() + timedelta(days=30))
        for _ in range(5):
            deduct_vial_from_box(self.user, box.pk)
        with self.assertRaises(InsulinBox.DoesNotExist):
            InsulinBox.objects.get(pk=box.pk)
        self.assertEqual(InsulinBox.objects.filter(user=self.user).count(), 0)

    def test_rejects_nonexistent_box(self):
        with self.assertRaises(ValueError) as ctx:
            deduct_vial_from_box(self.user, 99999)
        self.assertIn("does not exist", str(ctx.exception))

    def test_rejects_depleted_box(self):
        box = add_insulin_box(self.user, date.today() + timedelta(days=30))
        for _ in range(5):
            deduct_vial_from_box(self.user, box.pk)
        with self.assertRaises(ValueError):
            deduct_vial_from_box(self.user, box.pk)

    def test_tracks_correct_remaining_after_multiple_deductions(self):
        box = add_insulin_box(self.user, date.today() + timedelta(days=30))
        deduct_vial_from_box(self.user, box.pk)
        deduct_vial_from_box(self.user, box.pk)
        deduct_vial_from_box(self.user, box.pk)
        box.refresh_from_db()
        self.assertEqual(box.vials_remaining, 2)


class TestStockMutations(UserTestCase):
    def test_add_stock_increases_quantity(self):
        add_stock(self.user, SupplyType.PUMP_SITES, 3)
        supply = TrackedSupply.objects.get(
            user=self.user, supply_type=SupplyType.PUMP_SITES
        )
        self.assertEqual(supply.quantity, 3)

    def test_add_stock_rejects_negative_count(self):
        with self.assertRaises(ValueError):
            add_stock(self.user, SupplyType.PUMP_SITES, -1)

    def test_add_stock_rejects_unknown_supply_type(self):
        with self.assertRaises(ValueError):
            add_stock(self.user, "NONEXISTENT", 1)

    def test_edit_stock_sets_explicit_quantity(self):
        edit_stock(self.user, SupplyType.PUMP_SITES, 9)
        supply = TrackedSupply.objects.get(
            user=self.user, supply_type=SupplyType.PUMP_SITES
        )
        self.assertEqual(supply.quantity, 9)

    def test_edit_stock_rejects_negative_quantity(self):
        with self.assertRaises(ValueError):
            edit_stock(self.user, SupplyType.PUMP_SITES, -1)


class TestRemoveStockDate(UserTestCase):
    def test_sets_last_used_at_on_removal(self):
        init_supplies(self.user)
        add_stock(self.user, SupplyType.PUMP_SITES, 5)
        before = timezone.localdate() - timedelta(days=1)
        supply = TrackedSupply.objects.get(
            user=self.user, supply_type=SupplyType.PUMP_SITES
        )
        supply.last_used_at = before
        supply.save()

        remove_stock(self.user, SupplyType.PUMP_SITES)
        supply.refresh_from_db()
        self.assertGreater(supply.last_used_at, before)

    def test_updates_last_used_at_on_each_removal(self):
        init_supplies(self.user)
        add_stock(self.user, SupplyType.PUMP_SITES, 5)
        supply = TrackedSupply.objects.get(
            user=self.user, supply_type=SupplyType.PUMP_SITES
        )
        supply.last_used_at = date(2020, 1, 1)
        supply.save()

        remove_stock(self.user, SupplyType.PUMP_SITES)
        remove_stock(self.user, SupplyType.PUMP_SITES)
        supply.refresh_from_db()
        self.assertEqual(supply.last_used_at, timezone.localdate())


class TestCalculateEstimatedChangeDates(UserTestCase):
    def test_returns_date_objects(self):
        init_supplies(self.user)
        supply = TrackedSupply.objects.get(
            user=self.user, supply_type=SupplyType.PUMP_SITES
        )
        supply.last_used_at = date(2025, 1, 1)
        supply.save()

        dates = calculate_estimated_change_dates(self.user, SupplyType.PUMP_SITES)
        self.assertTrue(all(isinstance(d, date) and not hasattr(d, 'hour') for d in dates))

    def test_returns_empty_list_when_no_last_used_at(self):
        init_supplies(self.user)
        supply = TrackedSupply.objects.get(
            user=self.user, supply_type=SupplyType.PUMP_SITES
        )
        supply.last_used_at = None
        supply.save()

        dates = calculate_estimated_change_dates(self.user, SupplyType.PUMP_SITES)
        self.assertEqual(dates, [])

    def test_returns_empty_list_when_quantity_is_zero(self):
        init_supplies(self.user)
        supply = TrackedSupply.objects.get(
            user=self.user, supply_type=SupplyType.PUMP_SITES
        )
        supply.last_used_at = date(2025, 1, 1)
        supply.quantity = 0
        supply.save()

        dates = calculate_estimated_change_dates(self.user, SupplyType.PUMP_SITES)
        self.assertEqual(dates, [])

    def test_returns_correct_number_of_dates(self):
        init_supplies(self.user)
        supply = TrackedSupply.objects.get(
            user=self.user, supply_type=SupplyType.PUMP_SITES
        )
        supply.last_used_at = date(2025, 1, 1)
        supply.quantity = 3
        supply.save()

        dates = calculate_estimated_change_dates(self.user, SupplyType.PUMP_SITES)
        self.assertEqual(len(dates), 3)

    def test_returns_sorted_dates(self):
        init_supplies(self.user)
        supply = TrackedSupply.objects.get(
            user=self.user, supply_type=SupplyType.PUMP_SITES
        )
        supply.last_used_at = date(2025, 1, 1)
        supply.quantity = 4
        supply.save()

        dates = calculate_estimated_change_dates(self.user, SupplyType.PUMP_SITES)
        self.assertEqual(dates, sorted(dates))

    def test_raises_value_error_for_unknown_supply_type(self):
        with self.assertRaises(ValueError):
            calculate_estimated_change_dates(self.user, "NONEXISTENT")


class TestAddInsulinBoxDateParsing(UserTestCase):
    def test_parses_isoformat_date_string(self):
        exp_date = date(2026, 12, 15)
        box = add_insulin_box(self.user, exp_date.isoformat())
        self.assertEqual(box.expiration_date, exp_date)

    def test_rejects_date_with_spaces(self):
        with self.assertRaises(ValueError):
            add_insulin_box(self.user, "2026-12-15 ")

    def test_rejects_slash_separator(self):
        with self.assertRaises(ValueError):
            add_insulin_box(self.user, "2026/12/15")

    def test_accepts_date_object_directly(self):
        exp_date = date(2027, 6, 1)
        box = add_insulin_box(self.user, exp_date)
        self.assertEqual(box.expiration_date, exp_date)

    def test_rejects_negative_year_string(self):
        with self.assertRaises(ValueError):
            add_insulin_box(self.user, "-0001-01-01")


class TestUserSeeding(UserTestCase):
    def test_creating_user_seeds_both_supplies(self):
        supply_types = set(
            TrackedSupply.objects.filter(user=self.user).values_list(
                'supply_type', flat=True
            )
        )
        self.assertEqual(
            supply_types, {SupplyType.PUMP_SITES, SupplyType.CGMS}
        )

    def test_seeded_supplies_use_expected_intervals(self):
        pump = TrackedSupply.objects.get(
            user=self.user, supply_type=SupplyType.PUMP_SITES
        )
        cgms = TrackedSupply.objects.get(
            user=self.user, supply_type=SupplyType.CGMS
        )
        self.assertEqual(pump.usage_interval_days, 3)
        self.assertEqual(cgms.usage_interval_days, 15)

    def test_init_supplies_is_idempotent(self):
        created = init_supplies(self.user)
        self.assertEqual(created, 0)
        self.assertEqual(
            TrackedSupply.objects.filter(user=self.user).count(), 2
        )


class TestSupplyIsolation(UserTestCase):
    def setUp(self):
        super().setUp()
        self.other = User.objects.create_user(username='bob', password='pw')

    def test_users_have_independent_supplies(self):
        add_stock(self.user, SupplyType.PUMP_SITES, 4)
        mine = TrackedSupply.objects.get(
            user=self.user, supply_type=SupplyType.PUMP_SITES
        )
        theirs = TrackedSupply.objects.get(
            user=self.other, supply_type=SupplyType.PUMP_SITES
        )
        self.assertEqual(mine.quantity, 4)
        self.assertEqual(theirs.quantity, 0)

    def test_remove_stock_only_affects_owner(self):
        add_stock(self.user, SupplyType.PUMP_SITES, 2)
        remove_stock(self.user, SupplyType.PUMP_SITES)
        self.assertEqual(
            TrackedSupply.objects.get(
                user=self.user, supply_type=SupplyType.PUMP_SITES
            ).quantity,
            1,
        )
        self.assertEqual(
            TrackedSupply.objects.get(
                user=self.other, supply_type=SupplyType.PUMP_SITES
            ).quantity,
            0,
        )

    def test_boxes_are_isolated_between_users(self):
        add_insulin_box(self.user, date.today() + timedelta(days=10))
        add_insulin_box(self.other, date.today() + timedelta(days=20))
        mine = get_soonest_expiring_boxes(self.user)
        theirs = get_soonest_expiring_boxes(self.other)
        self.assertEqual(len(mine), 1)
        self.assertEqual(len(theirs), 1)
        self.assertNotEqual(mine[0].pk, theirs[0].pk)

    def test_cannot_deduct_other_users_box(self):
        box = add_insulin_box(self.other, date.today() + timedelta(days=10))
        with self.assertRaises(ValueError):
            deduct_vial_from_box(self.user, box.pk)
        box.refresh_from_db()
        self.assertEqual(box.vials_remaining, 5)

    def test_cannot_read_other_users_estimates(self):
        self.other.tracked_supplies.update(last_used_at=date(2025, 1, 1), quantity=3)
        dates = calculate_estimated_change_dates(self.user, SupplyType.PUMP_SITES)
        self.assertEqual(dates, [])


class TestPerUserSupplyConstraint(UserTestCase):
    def test_two_users_can_share_the_same_supply_type(self):
        User.objects.create_user(username='bob', password='pw')
        self.assertEqual(
            TrackedSupply.objects.filter(
                supply_type=SupplyType.PUMP_SITES
            ).count(),
            2,
        )

    def test_duplicate_supply_type_for_same_user_is_rejected(self):
        with self.assertRaises(IntegrityError):
            TrackedSupply.objects.create(
                user=self.user,
                supply_type=SupplyType.PUMP_SITES,
                usage_interval_days=3,
            )


class TestLoginPage(UserTestCase):
    def test_login_page_renders(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Log in')


class TestDashboardView(UserTestCase):
    def test_redirects_anonymous_user_to_login(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_shows_logged_in_users_own_data(self):
        add_stock(self.user, SupplyType.PUMP_SITES, 7)
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, SupplyType.PUMP_SITES.label)

    def test_does_not_show_other_users_boxes(self):
        other = User.objects.create_user(username='bob', password='pw')
        add_insulin_box(other, date.today() + timedelta(days=5))
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'bob')


def messages_for(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


class TestUseSupply(UserTestCase):
    def setUp(self):
        super().setUp()
        add_stock(self.user, SupplyType.PUMP_SITES, 2)
        self.client.force_login(self.user)
        self.url = reverse('use_supply', args=[SupplyType.PUMP_SITES.value])

    def test_decrements_quantity_by_one(self):
        self.client.post(self.url)
        supply = TrackedSupply.objects.get(
            user=self.user, supply_type=SupplyType.PUMP_SITES
        )
        self.assertEqual(supply.quantity, 1)

    def test_stamps_last_used_at_with_today(self):
        self.client.post(self.url)
        supply = TrackedSupply.objects.get(
            user=self.user, supply_type=SupplyType.PUMP_SITES
        )
        self.assertEqual(supply.last_used_at, timezone.localdate())

    def test_redirects_to_dashboard(self):
        response = self.client.post(self.url)
        self.assertRedirects(response, reverse('dashboard'))

    def test_flashes_success_message(self):
        response = self.client.post(self.url)
        self.assertTrue(any('Pump Sites' in m for m in messages_for(response)))

    def test_rejects_use_when_quantity_is_zero(self):
        url = reverse('use_supply', args=[SupplyType.CGMS.value])
        response = self.client.post(url)
        supply = TrackedSupply.objects.get(
            user=self.user, supply_type=SupplyType.CGMS
        )
        self.assertEqual(supply.quantity, 0)
        self.assertTrue(any('no stock remaining' in m for m in messages_for(response)))

    def test_unknown_supply_type_returns_404(self):
        response = self.client.post(reverse('use_supply', args=['bogus']))
        self.assertEqual(response.status_code, 404)

    def test_get_is_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_anonymous_user_is_redirected_to_login(self):
        self.client.logout()
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)


class TestUseVial(UserTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.box = add_insulin_box(self.user, date.today() + timedelta(days=30))

    def test_decrements_vials_remaining(self):
        self.client.post(reverse('use_vial', args=[self.box.pk]))
        self.box.refresh_from_db()
        self.assertEqual(self.box.vials_remaining, 4)

    def test_redirects_to_dashboard(self):
        response = self.client.post(reverse('use_vial', args=[self.box.pk]))
        self.assertRedirects(response, reverse('dashboard'))

    def test_flashes_success_message(self):
        response = self.client.post(reverse('use_vial', args=[self.box.pk]))
        self.assertTrue(any('vial' in m.lower() for m in messages_for(response)))

    def test_cannot_use_another_users_box(self):
        other = User.objects.create_user(username='bob', password='pw')
        their_box = add_insulin_box(other, date.today() + timedelta(days=10))
        response = self.client.post(reverse('use_vial', args=[their_box.pk]))
        their_box.refresh_from_db()
        self.assertEqual(their_box.vials_remaining, 5)
        self.assertTrue(any('does not exist' in m for m in messages_for(response)))

    def test_nonexistent_box_flashes_error(self):
        response = self.client.post(reverse('use_vial', args=[99999]))
        self.assertTrue(any('does not exist' in m for m in messages_for(response)))

    def test_get_is_not_allowed(self):
        response = self.client.get(reverse('use_vial', args=[self.box.pk]))
        self.assertEqual(response.status_code, 405)

    def test_anonymous_user_is_redirected_to_login(self):
        self.client.logout()
        response = self.client.post(reverse('use_vial', args=[self.box.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)


class TestAddSuppliesPage(UserTestCase):
    def test_renders_for_logged_in_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('add_supplies'))
        self.assertEqual(response.status_code, 200)

    def test_redirects_anonymous_user_to_login(self):
        response = self.client.get(reverse('add_supplies'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)


class TestAddSupply(UserTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.url = reverse('add_supply', args=[SupplyType.PUMP_SITES.value])

    def test_adds_entered_quantity(self):
        self.client.post(self.url, {'count': '5'})
        supply = TrackedSupply.objects.get(
            user=self.user, supply_type=SupplyType.PUMP_SITES
        )
        self.assertEqual(supply.quantity, 5)

    def test_redirects_to_add_page(self):
        response = self.client.post(self.url, {'count': '1'})
        self.assertRedirects(response, reverse('add_supplies'))

    def test_flashes_success_message(self):
        response = self.client.post(self.url, {'count': '5'})
        self.assertTrue(any('5' in m for m in messages_for(response)))

    def test_rejects_non_numeric_count(self):
        response = self.client.post(self.url, {'count': 'abc'})
        supply = TrackedSupply.objects.get(
            user=self.user, supply_type=SupplyType.PUMP_SITES
        )
        self.assertEqual(supply.quantity, 0)
        self.assertTrue(messages_for(response))

    def test_rejects_negative_count(self):
        response = self.client.post(self.url, {'count': '-1'})
        supply = TrackedSupply.objects.get(
            user=self.user, supply_type=SupplyType.PUMP_SITES
        )
        self.assertEqual(supply.quantity, 0)
        self.assertTrue(messages_for(response))

    def test_unknown_supply_type_returns_404(self):
        response = self.client.post(reverse('add_supply', args=['bogus']), {'count': '1'})
        self.assertEqual(response.status_code, 404)

    def test_get_is_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_anonymous_user_is_redirected_to_login(self):
        self.client.logout()
        response = self.client.post(self.url, {'count': '1'})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)


class TestAddBox(UserTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.url = reverse('add_box')

    def test_creates_box_with_expiration_date(self):
        exp = date.today() + timedelta(days=30)
        self.client.post(self.url, {'expiration_date': exp.isoformat()})
        box = InsulinBox.objects.get(user=self.user)
        self.assertEqual(box.expiration_date, exp)
        self.assertEqual(box.vials_remaining, 5)

    def test_redirects_to_add_page(self):
        exp = date.today() + timedelta(days=30)
        response = self.client.post(self.url, {'expiration_date': exp.isoformat()})
        self.assertRedirects(response, reverse('add_supplies'))

    def test_flashes_success_message(self):
        exp = date.today() + timedelta(days=30)
        response = self.client.post(self.url, {'expiration_date': exp.isoformat()})
        self.assertTrue(
            any(exp.isoformat() in m for m in messages_for(response))
        )

    def test_rejects_past_expiration_date(self):
        past = date.today() - timedelta(days=1)
        response = self.client.post(self.url, {'expiration_date': past.isoformat()})
        self.assertEqual(InsulinBox.objects.filter(user=self.user).count(), 0)
        self.assertTrue(any('past' in m for m in messages_for(response)))

    def test_rejects_missing_expiration_date(self):
        response = self.client.post(self.url, {})
        self.assertEqual(InsulinBox.objects.filter(user=self.user).count(), 0)
        self.assertTrue(messages_for(response))

    def test_get_is_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_anonymous_user_is_redirected_to_login(self):
        self.client.logout()
        response = self.client.post(self.url, {'expiration_date': date.today().isoformat()})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)


class TestDashboardActionControls(UserTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_shows_use_button_when_stock_available(self):
        add_stock(self.user, SupplyType.PUMP_SITES, 1)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(
            response, reverse('use_supply', args=[SupplyType.PUMP_SITES.value])
        )

    def test_omits_use_button_when_stock_is_empty(self):
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(
            response, reverse('use_supply', args=[SupplyType.CGMS.value])
        )

    def test_shows_use_vial_button_for_each_box(self):
        box = add_insulin_box(self.user, date.today() + timedelta(days=30))
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, reverse('use_vial', args=[box.pk]))

    def test_links_to_add_page(self):
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, reverse('add_supplies'))
