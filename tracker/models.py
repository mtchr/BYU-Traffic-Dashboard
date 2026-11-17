from django.db import models

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
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name='layoffs')
    active_date = models.DateField()
    all_day = models.BooleanField(default=False)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)

    def __str__(self):
        return f"Layoff for {self.lot.name} on {self.active_date}"