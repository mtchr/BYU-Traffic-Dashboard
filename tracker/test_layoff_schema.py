from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, TestCase, TransactionTestCase

from .models import Layoff, Lot, PatrolEntry, Vehicle, VehicleLog


START = datetime(2026, 11, 27, 14)
MIDNIGHT = datetime(2026, 11, 28)


class LayoffSchemaTests(TestCase):
    def setUp(self):
        self.lot = Lot.objects.create(
            name='Schema test lot',
            polygon_coords=[[0, 0], [0, 1], [1, 0]],
        )
        self.user = get_user_model().objects.create_user(
            username='layoff-editor'
        )

    def record(self, **changes):
        values = dict(
            lot=self.lot,
            starts_at=START,
            ends_at=MIDNIGHT,
            all_day=True,
            created_by=self.user,
        )
        values.update(changes)
        with patch('django.utils.timezone.now', return_value=START):
            return Layoff.objects.create(**values)

    def test_denver_naive_time_convention_is_unchanged(self):
        self.assertFalse(settings.USE_TZ)
        self.assertEqual(settings.TIME_ZONE, 'America/Denver')

        record = self.record()
        record.refresh_from_db()

        self.assertEqual(record.starts_at, START)
        self.assertEqual(record.ends_at, MIDNIGHT)
        self.assertEqual(record.created_at, START)
        record.full_clean()
        self.assertIn('Schema test lot', str(record))

    def test_end_must_be_after_start_in_model_and_database(self):
        for end in [START, START - timedelta(minutes=1)]:
            with self.subTest(end=end):
                obj = Layoff(
                    lot=self.lot, starts_at=START, ends_at=end
                )
                with self.assertRaises(ValidationError):
                    obj.full_clean()

                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.record(ends_at=end, all_day=False)

    def test_end_cannot_extend_past_midnight(self):
        obj = Layoff(
            lot=self.lot,
            starts_at=START,
            ends_at=MIDNIGHT + timedelta(minutes=1),
        )
        with self.assertRaisesMessage(ValidationError, 'past midnight'):
            obj.full_clean()

    def test_all_day_requires_midnight_but_timed_window_does_not(self):
        obj = Layoff(
            lot=self.lot,
            starts_at=START,
            ends_at=START + timedelta(hours=1),
            all_day=True,
        )
        with self.assertRaisesMessage(ValidationError, 'All Day'):
            obj.full_clean()

        obj.all_day = False
        obj.full_clean()

    def test_current_settings_reject_offset_inputs_until_normalized(self):
        obj = Layoff(
            lot=self.lot,
            starts_at=START.replace(tzinfo=datetime_timezone.utc),
            ends_at=MIDNIGHT.replace(tzinfo=datetime_timezone.utc),
        )
        with self.assertRaisesMessage(ValidationError, 'Denver local times'):
            obj.full_clean()

    def test_history_remains_valid_on_a_later_day(self):
        record = self.record()

        with patch(
            'django.utils.timezone.now',
            return_value=START + timedelta(days=2),
        ):
            record.full_clean()

        self.assertEqual(Layoff.objects.count(), 1)

    def test_cancellation_keeps_original_schedule_and_creation(self):
        record = self.record()
        record.cancelled_at = START + timedelta(minutes=30)
        record.cancelled_by = self.user
        record.version += 1

        record.full_clean()
        record.save(
            update_fields=['cancelled_at', 'cancelled_by', 'version']
        )
        record.refresh_from_db()

        self.assertEqual(record.starts_at, START)
        self.assertEqual(record.ends_at, MIDNIGHT)
        self.assertEqual(record.created_at, START)
        self.assertEqual(
            record.cancelled_at, START + timedelta(minutes=30)
        )
        self.assertEqual(record.version, 2)

    def test_cancelling_before_scheduled_start_is_allowed(self):
        record = self.record(
            starts_at=START + timedelta(hours=1)
        )
        record.cancelled_at = START + timedelta(minutes=5)
        record.cancelled_by = self.user

        record.full_clean()
        record.save(update_fields=['cancelled_at', 'cancelled_by'])

    def test_database_rejects_cancellation_before_creation(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.record(
                cancelled_at=START - timedelta(seconds=1)
            )

    def test_database_rejects_cancellation_actor_without_time(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.record(cancelled_by=self.user)

    def test_database_rejects_zero_version(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.record(version=0)

    def test_lot_and_replaced_history_are_protected(self):
        original = self.record()

        with self.assertRaises(ProtectedError):
            self.lot.delete()

        replacement = self.record(
            starts_at=START + timedelta(hours=1),
            replaces=original,
        )

        with self.assertRaises(ProtectedError):
            original.delete()

        self.assertEqual(replacement.replaces_id, original.pk)

    def test_removing_actor_account_does_not_delete_history(self):
        record = self.record(
            cancelled_at=START + timedelta(minutes=5),
            cancelled_by=self.user,
        )

        self.user.delete()
        record.refresh_from_db()

        self.assertIsNone(record.created_by_id)
        self.assertIsNone(record.cancelled_by_id)
        self.assertIsNotNone(record.cancelled_at)

    def test_authorized_staff_can_view_but_admin_cannot_rewrite_history(self):
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])

        permission = Permission.objects.get(
            content_type__app_label='tracker',
            codename='manage_layoffs',
        )
        self.user.user_permissions.add(permission)

        request = RequestFactory().get('/admin/tracker/layoff/')
        request.user = get_user_model().objects.get(pk=self.user.pk)
        model_admin = admin.site._registry[Layoff]

        self.assertTrue(model_admin.has_view_permission(request))
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))
        self.assertEqual(
            set(model_admin.get_readonly_fields(request)),
            {field.name for field in Layoff._meta.fields},
        )

        self.client.force_login(request.user)
        record = self.record()

        self.assertEqual(
            self.client.get('/admin/tracker/layoff/').status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                f'/admin/tracker/layoff/{record.pk}/change/'
            ).status_code,
            200,
        )

        before = Layoff.objects.values().get(pk=record.pk)

        for path in [
            '/admin/tracker/layoff/add/',
            f'/admin/tracker/layoff/{record.pk}/change/',
            f'/admin/tracker/layoff/{record.pk}/delete/',
        ]:
            with self.subTest(path=path), self.assertLogs(
                'django.request', level='WARNING'
            ):
                response = self.client.post(path, data={})
                self.assertEqual(response.status_code, 403)

        self.assertEqual(
            Layoff.objects.values().get(pk=record.pk),
            before,
        )


class LayoffMigrationTests(TransactionTestCase):
    old_target = ('tracker', '0002_manage_layoff_permissions')
    new_target = ('tracker', '0003_layoff_schedule_history')

    def migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.migrate([target])
        return executor.loader.project_state([target]).apps

    def test_empty_table_round_trip_preserves_unrelated_patrol_data(self):
        permission = Permission.objects.get(
            content_type__app_label='tracker',
            codename='manage_layoffs',
        )
        manager = get_user_model().objects.create_user(
            username='existing-manager'
        )
        manager.user_permissions.add(permission)

        lot = Lot.objects.create(
            name='Existing patrol lot', polygon_coords=[]
        )
        vehicle = Vehicle.objects.create(vehicle_id='PRESERVE')
        now = datetime(2026, 11, 27, 10)

        with patch('django.utils.timezone.now', return_value=now):
            log = VehicleLog.objects.create(
                vehicle=vehicle, latitude=1, longitude=2
            )

        entry = PatrolEntry.objects.create(
            vehicle=vehicle,
            lot=lot,
            enter_time=now,
            exit_time=now + timedelta(seconds=60),
            duration_seconds=60,
            shift_name='Morning',
            shift_date=now.date(),
            status='completed',
        )

        before_log = VehicleLog.objects.values().get(pk=log.pk)
        before_entry = PatrolEntry.objects.values().get(pk=entry.pk)

        self.migrate(self.old_target)
        self.migrate(self.new_target)

        self.assertEqual(
            VehicleLog.objects.values().get(pk=log.pk),
            before_log,
        )
        self.assertEqual(
            PatrolEntry.objects.values().get(pk=entry.pk),
            before_entry,
        )
        self.assertEqual(
            Vehicle.objects.get(pk=vehicle.pk).vehicle_id,
            'PRESERVE',
        )
        self.assertEqual(Layoff.objects.count(), 0)
        self.assertTrue(
            get_user_model().objects.get(pk=manager.pk).has_perm(
                'tracker.manage_layoffs'
            )
        )

    def test_forward_guard_preserves_unexpected_legacy_rows(self):
        old_apps = self.migrate(self.old_target)
        OldLot = old_apps.get_model('tracker', 'Lot')
        OldLayoff = old_apps.get_model('tracker', 'Layoff')

        lot = OldLot.objects.create(
            name='Legacy guard lot', polygon_coords=[]
        )
        legacy = OldLayoff.objects.create(
            lot=lot,
            active_date=START.date(),
            all_day=True,
        )

        try:
            with self.assertRaisesMessage(
                RuntimeError, 'Layoff rows exist'
            ):
                self.migrate(self.new_target)

            self.assertEqual(
                OldLayoff.objects.get(pk=legacy.pk).active_date,
                START.date(),
            )

            with connection.cursor() as cursor:
                columns = {
                    col.name
                    for col in connection.introspection.get_table_description(
                        cursor, 'tracker_layoff'
                    )
                }

            self.assertIn('active_date', columns)
            self.assertNotIn('starts_at', columns)
        finally:
            OldLayoff.objects.all().delete()
            self.migrate(self.new_target)

    def test_reverse_guard_preserves_new_history(self):
        lot = Lot.objects.create(
            name='New history guard lot', polygon_coords=[]
        )

        with patch('django.utils.timezone.now', return_value=START):
            record = Layoff.objects.create(
                lot=lot,
                starts_at=START,
                ends_at=MIDNIGHT,
                all_day=True,
            )

        before = Layoff.objects.values().get(pk=record.pk)

        with self.assertRaisesMessage(
            RuntimeError, 'Layoff rows exist'
        ):
            self.migrate(self.old_target)

        self.assertEqual(
            Layoff.objects.values().get(pk=record.pk),
            before,
        )