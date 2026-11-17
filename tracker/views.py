import json
from datetime import timedelta

from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from .models import Lot, Vehicle, VehicleLog, PatrolEntry, LotEvent, Layoff
from .utils import get_current_shift_info
from .geofence import get_lot
from . import lot_polygons
from django.contrib.auth.decorators import login_required

@csrf_exempt
def update_location(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # 1. Translate string from geofence into the actual Lot database object
            calculated_lot_name = get_lot(data['lat'], data['lon'])
            calculated_lot = Lot.objects.filter(name=calculated_lot_name).first() if calculated_lot_name else None
            
            thresholds = getattr(lot_polygons, 'COMPLETION_THRESHOLDS', {"default": 30})
            verification_time = getattr(lot_polygons, 'VERIFICATION_TIME', 15)
            
            shift_name, shift_date, shift_start_time = get_current_shift_info()
            
            vehicle_obj = Vehicle.objects.filter(vehicle_id=data['vehicle_id']).first()
            current_time = timezone.now()
            
            if vehicle_obj:
                entry_time = vehicle_obj.lot_entry_time
                last_visited = vehicle_obj.last_visited_lot
                drift_start = vehicle_obj.drift_start_time
                
                # --- DRIFT PROTECTION LOGIC ---
                if vehicle_obj.current_lot:
                    if calculated_lot == vehicle_obj.current_lot:
                        # Pinging safely inside the lot. Clear any drift warnings.
                        drift_start = None
                    else:
                        # Pinging OUTSIDE the lot.
                        if not drift_start:
                            # Start the 15-second grace period
                            drift_start = current_time
                            calculated_lot = vehicle_obj.current_lot 
                        else:
                            # Drift confirmed?
                            drift_duration = (current_time - drift_start).total_seconds()
                            if drift_duration >= 15:
                                actual_exit_time = drift_start
                                duration = (actual_exit_time - vehicle_obj.lot_entry_time).total_seconds()
                                
                                # Safety fallback if a lot doesn't exist in thresholds
                                lot_name_key = vehicle_obj.current_lot.name if vehicle_obj.current_lot else "default"
                                req_time = thresholds.get(lot_name_key, thresholds.get("default", 30))
                                
                                # Create the PatrolEntry using the new fields!
                                if duration >= req_time or duration >= verification_time:
                                    status = 'completed' if duration >= req_time else 'partial'
                                    PatrolEntry.objects.create(
                                        lot=vehicle_obj.current_lot, 
                                        vehicle=vehicle_obj,
                                        enter_time=vehicle_obj.lot_entry_time,
                                        exit_time=actual_exit_time,
                                        duration_seconds=int(duration), 
                                        shift_name=shift_name,
                                        shift_date=shift_date, 
                                        status=status
                                    )
                                
                                last_visited = vehicle_obj.current_lot
                                drift_start = None
                                entry_time = current_time if calculated_lot else None
                            else:
                                calculated_lot = vehicle_obj.current_lot
                else:
                    if calculated_lot:
                        entry_time = current_time
                        drift_start = None
                        
                # 2. Update Vehicle State
                vehicle_obj.last_lat = data['lat']
                vehicle_obj.last_lon = data['lon']
                vehicle_obj.current_lot = calculated_lot
                vehicle_obj.lot_entry_time = entry_time
                vehicle_obj.last_visited_lot = last_visited
                vehicle_obj.drift_start_time = drift_start
                vehicle_obj.save()

            # 3. Log raw breadcrumb
            VehicleLog.objects.create(
                vehicle_id=data['vehicle_id'], 
                latitude=data['lat'], 
                longitude=data['lon'], 
                lot_name=calculated_lot_name # Stores the string so GPS never crashes on missing FKs
            )
            VehicleLog.objects.filter(timestamp__lt=shift_start_time).delete()
            return JsonResponse({"status": "success"})
            
        except Exception as e:
            import traceback
            traceback.print_exc() # Prints exact error to your terminal for debugging
            return JsonResponse({"status": "error", "message": str(e)}, status=400)
    return JsonResponse({"status": "invalid_method"}, status=405)

# -------------------------------------------
def home(request):
    return HttpResponse("<h1>PatrolCenter is Online</h1><p>Go to /admin to manage vehicles.</p>")

@login_required(login_url='/accounts/login/')
def dashboard(request):
    vehicles = Vehicle.objects.all()
    return render(request, 'tracker/dashboard.html', {'vehicles': vehicles})
# -------------------------------------------
@login_required(login_url='/admin/login/')
def api_vehicles(request):
    vehicles = Vehicle.objects.all()
    data = []
    for v in vehicles:
        data.append({
            'vehicle_id': v.vehicle_id,
            'latitude': v.last_lat,
            'longitude': v.last_lon,
            # Because current_lot is an Object now, we grab its .name safely
            'lot': v.current_lot.name if v.current_lot else None,  
            'lot_entry_time': v.lot_entry_time.isoformat() if v.lot_entry_time else None,
            'last_update': v.last_update.isoformat() if v.last_update else None,
        })
    return JsonResponse(data, safe=False)

def api_polygons(request):
    return JsonResponse({
        "polygons": lot_polygons.CAMPUS_LOTS,
        "thresholds": getattr(lot_polygons, 'COMPLETION_THRESHOLDS', {"default": 30}),
        "verification_time": getattr(lot_polygons, 'VERIFICATION_TIME', 15)
    })

# -------------------------------------------

def merge_intervals(intervals):
    if not intervals: return 0
    intervals.sort(key=lambda x: x[0])
    merged = [intervals[0]]
    for current in intervals[1:]:
        last = merged[-1]
        if current[0] <= last[1]:
            merged[-1] = (last[0], max(last[1], current[1]))
        else:
            merged.append(current)
    return sum((end - start).total_seconds() for start, end in merged)

def api_completed_patrols(request):
    shift_name, shift_date, _ = get_current_shift_info()
    
    day_ledgers = PatrolEntry.objects.filter(shift_date=shift_date).select_related('lot').order_by('enter_time')
    live_vehicles = Vehicle.objects.exclude(current_lot__isnull=True).select_related('current_lot')
    now = timezone.now()
    
    all_lots = {lot.name: lot.priority_level for lot in Lot.objects.filter(is_static_icon=False)}
    daily_run_counts = {lot_name: 0 for lot_name in all_lots.keys()}
    
    current_shift_intervals = {}
    current_status = {}
    previous_shifts_data = {}
    
    # NEW: Data structures to hold history for your (i) modals and exit times
    lot_entries_history = {}
    latest_exit_times = {}

    for entry in day_ledgers:
        lot_name = entry.lot.name
        
        if entry.status == 'completed':
            daily_run_counts[lot_name] += 1

        # Format exact times for the (i) modal
        def format_time(dt):
            return timezone.localtime(dt).strftime('%H:%M') if timezone.is_aware(dt) else dt.strftime('%H:%M')

        in_str = format_time(entry.enter_time)
        out_dt = entry.exit_time if entry.exit_time else now
        out_str = format_time(out_dt)
        
        lot_entries_history.setdefault(lot_name, []).append({"in": in_str, "out": out_str})
        
        # Track the absolute latest time the vehicle left the lot
        if not latest_exit_times.get(lot_name) or out_dt > latest_exit_times[lot_name]:
            latest_exit_times[lot_name] = out_dt

        if entry.shift_name == shift_name:
            current_shift_intervals.setdefault(lot_name, []).append((entry.enter_time, out_dt))
            if current_status.get(lot_name) != 'completed':
                current_status[lot_name] = entry.status
        else:
            mins, secs = divmod(entry.duration_seconds or 0, 60)
            previous_shifts_data[lot_name] = {
                "status": entry.status, 
                "time": f"{mins:02d}:{secs:02d}",
                "entries": lot_entries_history.get(lot_name, []),
                "last_completed": latest_exit_times[lot_name].isoformat()
            }

    for v in live_vehicles:
        if v.lot_entry_time and v.current_lot:
            lot_name = v.current_lot.name
            current_shift_intervals.setdefault(lot_name, []).append((v.lot_entry_time, now))
            
            # Show live active status inside the modal
            def format_time(dt):
                return timezone.localtime(dt).strftime('%H:%M') if timezone.is_aware(dt) else dt.strftime('%H:%M')
            in_str = format_time(v.lot_entry_time)
            lot_entries_history.setdefault(lot_name, []).append({"in": in_str, "out": "Active"})

    current_shift_data = {}
    for lot_name, intervals in current_shift_intervals.items():
        total_secs = merge_intervals(intervals)
        mins, secs = divmod(int(total_secs), 60)
        
        current_shift_data[lot_name] = {
            "status": current_status.get(lot_name, 'partial'),
            "time": f"{mins:02d}:{secs:02d}",
            "total_seconds": int(total_secs),
            "daily_runs": daily_run_counts[lot_name],
            "priority": all_lots.get(lot_name, 'low'),
            "entries": lot_entries_history.get(lot_name, []),
            "last_completed": latest_exit_times[lot_name].isoformat() if lot_name in latest_exit_times else None
        }

    for lot_name, data in previous_shifts_data.items():
        if lot_name not in current_shift_data:
            data["daily_runs"] = daily_run_counts.get(lot_name, 0)
            data["priority"] = all_lots.get(lot_name, 'low')

    for lot_name, priority in all_lots.items():
        if lot_name not in current_shift_data and lot_name not in previous_shifts_data:
            current_shift_data[lot_name] = {
                "status": "pending", "time": "--:--", "total_seconds": 0, "daily_runs": 0, "priority": priority, "entries": [], "last_completed": None
            }

    food_stop_count = day_ledgers.filter(lot__name__in=['CFA', 'MCD', 'CANES'], duration_seconds__gte=15).count()

    return JsonResponse({'current_shift': current_shift_data, 'previous_shifts': previous_shifts_data, 'food_stop_count': food_stop_count})
# -------------------------------------------

def api_vehicle_summary(request):
    shift_name, shift_date, shift_start = get_current_shift_info()
    now = timezone.now()
    elapsed_shift_seconds = max((now.replace(tzinfo=None) - shift_start.replace(tzinfo=None)).total_seconds(), 1)
    
    ledgers = PatrolEntry.objects.filter(shift_date=shift_date, shift_name=shift_name).select_related('vehicle')

    summary = {}
    for entry in ledgers:
        vid = entry.vehicle.vehicle_id # Get vehicle ID from the related object
        if vid not in summary:
            summary[vid] = {"total_seconds": 0, "completed_lots": 0, "partial_lots": 0}

        summary[vid]["total_seconds"] += (entry.duration_seconds or 0)
        
        if entry.status == 'completed':
            summary[vid]["completed_lots"] += 1
        elif entry.status == 'partial':
            summary[vid]["partial_lots"] += 1

    results = []
    for vid, data in summary.items():
        patrol_secs = min(data["total_seconds"], elapsed_shift_seconds)
        patrol_pct = (patrol_secs / elapsed_shift_seconds) * 100
        transit_pct = 100 - patrol_pct

        mins, secs = divmod(int(patrol_secs), 60)
        results.append({
            "vehicle_id": vid,
            "time_str": f"{mins:02d}:{secs:02d}",
            "completed_lots": data["completed_lots"],
            "patrol_pct": patrol_pct,
            "transit_pct": transit_pct
        })

    results.sort(key=lambda x: x["patrol_pct"], reverse=True)
    return JsonResponse(results, safe=False)

# -------------------------------------------
# HARDWARE INGESTION ENDPOINT (RASPBERRY PI)
# -------------------------------------------

@csrf_exempt
def ingest_gps(request):
    """Receives JSON data from the Raspberry Pi and saves it."""
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            vehicle_id = data.get('vehicle_id')
            lat = data.get('latitude')
            lng = data.get('longitude')
            
            # 1. Update the vehicle's current live position
            # get_or_create ensures that if a new Pi comes online, it builds a profile automatically
            vehicle, created = Vehicle.objects.get_or_create(
                vehicle_id=vehicle_id,
                defaults={'last_lat': lat, 'last_lon': lng}
            )
            
            if not created:
                vehicle.last_lat = lat
                vehicle.last_lon = lng
                
                # Note: When you are ready, you will insert your Shapely geofencing 
                # function right here to check if these new coords intersect a lot, 
                # and update vehicle.current_lot before saving!
                
                vehicle.save()
            
            # 2. Save the historical breadcrumb for the replay map
            # We use vehicle=vehicle here because VehicleLog expects the actual ForeignKey object
            VehicleLog.objects.create(
                vehicle=vehicle,
                latitude=lat,
                longitude=lng
            )
            
            return JsonResponse({'status': 'success', 'message': 'Location logged'}, status=200)
            
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
            
    return JsonResponse({'status': 'error', 'message': 'Only POST requests allowed'}, status=405)
