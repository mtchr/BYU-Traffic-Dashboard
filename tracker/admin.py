# * security & * Vehicle *
from django.contrib import admin
from .models import Lot, Vehicle, VehicleLog, PatrolEntry, LotEvent, Layoff

@admin.register(Lot)
class LotAdmin(admin.ModelAdmin):
    # Shows the priority level and whether it's a food stop right in the list
    list_display = ('name', 'priority_level', 'is_static_icon')
    list_filter = ('priority_level', 'is_static_icon')
    search_fields = ('name',)

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    # Keeps your live tracking view intact
    list_display = ('vehicle_id', 'is_active', 'current_lot', 'last_visited_lot', 'last_update')
    list_filter = ('is_active',)
    search_fields = ('vehicle_id',)

@admin.register(PatrolEntry)
class PatrolEntryAdmin(admin.ModelAdmin):
    # Shows exact entry/exit times and shift dates
    list_display = ('lot', 'vehicle', 'shift_date', 'enter_time', 'exit_time', 'status')
    list_filter = ('shift_date', 'status', 'lot')
    search_fields = ('vehicle__vehicle_id', 'lot__name')

@admin.register(Layoff)
class LayoffAdmin(admin.ModelAdmin):
    list_display = (
        'lot', 'starts_at', 'ends_at', 'all_day',
        'created_by', 'cancelled_at',
    )
    list_filter = ('all_day', 'starts_at')
    date_hierarchy = 'starts_at'
    search_fields = ('lot__name',)
    list_select_related = (
        'lot', 'created_by', 'cancelled_by', 'replaces',
    )
    readonly_fields = tuple(
        field.name for field in Layoff._meta.fields
    )

    def has_view_permission(self, request, obj=None):
        return (
            request.user.has_perm('tracker.manage_layoffs')
            or super().has_view_permission(request, obj)
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(LotEvent)
class LotEventAdmin(admin.ModelAdmin):
    list_display = ('lot', 'start_date', 'end_date')

@admin.register(VehicleLog)
class VehicleLogAdmin(admin.ModelAdmin):
    list_display = ('vehicle', 'lot_name', 'timestamp')
    list_filter = ('vehicle',)

# djang0912