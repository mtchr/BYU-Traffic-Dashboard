from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

# Create your models here.

class Lot(models.Model):
    name = models.CharField(max_length=50, unique=True)
    polygon_coords = models.JSONField()
    priority_level = models.CharField(
        max_length=10, 
        choices=[('high', 'High'), ('medium', 'Medium'), ('low', 'Low')],
        default='low'
    )
    is_static_icon = models.BooleanField(default=False)

    def __str__(self):
        return self.name

class Vehicle(models.Model):
    # Hardware/Entity config
    vehicle_id = models.CharField(max_length=50, primary_key=True)
    is_active = models.BooleanField(default=True)
    
    # Live State (For fast Leaflet map polling)
    last_lat = models.FloatField(null=True, blank=True)
    last_lon = models.FloatField(null=True, blank=True)
    current_lot = models.ForeignKey(Lot, on_delete=models.SET_NULL, null=True, blank=True, related_name='current_vehicles')
    lot_entry_time = models.DateTimeField(null=True, blank=True)
    last_visited_lot = models.ForeignKey(Lot, on_delete=models.SET_NULL, null=True, blank=True, related_name='last_visited_by')
    drift_start_time = models.DateTimeField(null=True, blank=True)
    last_update = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.vehicle_id

class VehicleLog(models.Model):
    # The raw hardware firehose (Breadcrumb trail)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='logs') 
    latitude = models.FloatField()
    longitude = models.FloatField()
    # Stored as a string so raw GPS ingestion doesn't fail on a Foreign Key constraint if a boundary is slightly off
    lot_name = models.CharField(max_length=50, null=True, blank=True) 
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.vehicle.vehicle_id} at {self.timestamp.strftime('%H:%M:%S')}"

class PatrolEntry(models.Model):
    # The finalized, calculated shift events (Replaces PatrolLedger)
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name='entries')
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='patrols')
    
    enter_time = models.DateTimeField()
    exit_time = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)
    
    shift_name = models.CharField(max_length=20, db_index=True, null=True, blank=True)
    shift_date = models.DateField(db_index=True, null=True, blank=True)
    status = models.CharField(max_length=20, default='completed')

    class Meta:
        ordering = ['-enter_time']

    def __str__(self):
        return f"{self.vehicle.vehicle_id} in {self.lot.name} on {self.shift_date}"
    
    class Meta:
        verbose_name_plural = "Patrol Entries"

class LotEvent(models.Model):
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name='events')
    start_date = models.DateField()
    end_date = models.DateField()

    def __str__(self):
        return f"Event at {self.lot.name} ({self.start_date})"

class Layoff(models.Model):
    lot = models.ForeignKey(
        Lot, on_delete=models.PROTECT, related_name='layoffs'
    )
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField(db_index=True)
    all_day = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_layoffs',
        editable=False,
    )

    cancelled_at = models.DateTimeField(
        null=True, blank=True, editable=False
    )
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cancelled_layoffs',
        editable=False,
    )

    replaces = models.OneToOneField(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='replacement',
        editable=False,
    )
    version = models.PositiveIntegerField(default=1, editable=False)

    class Meta:
        ordering = ['-starts_at', '-pk']
        permissions = [
            ('manage_layoffs', 'Can manage layoffs'),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(ends_at__gt=models.F('starts_at')),
                name='layoff_end_after_start',
            ),
            models.CheckConstraint(
                check=models.Q(version__gte=1),
                name='layoff_version_at_least_one',
            ),
            models.CheckConstraint(
                check=(
                    models.Q(cancelled_at__isnull=True)
                    | models.Q(cancelled_at__gte=models.F('created_at'))
                ),
                name='layoff_cancellation_after_creation',
            ),
            models.CheckConstraint(
                check=(
                    models.Q(cancelled_by__isnull=True)
                    | models.Q(cancelled_at__isnull=False)
                ),
                name='layoff_cancel_actor_needs_time',
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.starts_at and self.ends_at:
            start_is_aware = timezone.is_aware(self.starts_at)
            end_is_aware = timezone.is_aware(self.ends_at)

            if start_is_aware != end_is_aware:
                errors['ends_at'] = (
                    'Start and end must use the same time convention.'
                )
            elif not settings.USE_TZ and start_is_aware:
                errors['starts_at'] = (
                    'Use Denver local times with the current settings.'
                )
            else:
                local_start = (
                    timezone.localtime(
                        self.starts_at, timezone.get_default_timezone()
                    )
                    if start_is_aware else self.starts_at
                )
                midnight = datetime.combine(
                    local_start.date() + timedelta(days=1), time.min
                )

                if start_is_aware:
                    midnight = timezone.make_aware(
                        midnight, timezone.get_default_timezone()
                    )

                if self.ends_at <= self.starts_at:
                    errors['ends_at'] = 'End must be after start.'
                elif self.ends_at > midnight:
                    errors['ends_at'] = (
                        'A layoff cannot extend past midnight.'
                    )
                elif self.all_day and self.ends_at != midnight:
                    errors['ends_at'] = 'All Day must end at midnight.'

        if self.cancelled_by_id and self.cancelled_at is None:
            errors['cancelled_at'] = (
                'A cancellation time is required for its actor.'
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return (
            f'Layoff for {self.lot.name}: '
            f'{self.starts_at} to {self.ends_at}'
        )
