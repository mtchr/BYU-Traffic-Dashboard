from django.utils import timezone
from datetime import datetime, time

def get_current_shift_info():
    """
    Returns a tuple containing:
    (shift_name, shift_date, shift_start_datetime)
    """
    now = timezone.now()
    
    # Safely handle both timezone-aware (USE_TZ=True) and naive (USE_TZ=False) datetimes
    if timezone.is_aware(now):
        now_local = timezone.localtime(now)
    else:
        now_local = now

    today = now_local.date()
    current_time = now_local.time()
    weekday = now_local.weekday()  # Monday is 0, Sunday is 6

    # Safe defaults for outside scheduled shifts
    shift_name = "Off-Shift"
    shift_date = today
    start_dt = datetime.combine(today, time.min)

    if weekday == 6:  # SUNDAY SCHEDULE
        t_8_00 = time(8, 0)
        t_11_00 = time(11, 0)
        t_14_00 = time(14, 0)

        if t_8_00 <= current_time < t_11_00:
            shift_name = "Morning"
            start_dt = datetime.combine(today, t_8_00)
        elif t_11_00 <= current_time < t_14_00:
            shift_name = "Afternoon"
            start_dt = datetime.combine(today, t_11_00)
            
    else:  # MONDAY - SATURDAY SCHEDULE
        t_1_00 = time(1, 0)
        t_5_00 = time(5, 0)
        t_6_45 = time(6, 45)
        t_10_15 = time(10, 15)
        t_13_15 = time(13, 15)
        t_17_00 = time(17, 0)

        if t_1_00 <= current_time < t_5_00:
            shift_name = "Overnight"
            start_dt = datetime.combine(today, t_1_00)
        elif t_6_45 <= current_time < t_10_15:
            shift_name = "Morning"
            start_dt = datetime.combine(today, t_6_45)
        elif t_10_15 <= current_time < t_13_15:
            shift_name = "Afternoon"
            start_dt = datetime.combine(today, t_10_15)
        elif t_13_15 <= current_time < t_17_00:
            shift_name = "Evening"
            start_dt = datetime.combine(today, t_13_15)

    # Attach timezone only if Django is configured with timezone support
    if timezone.is_aware(now):
        current_tz = timezone.get_current_timezone()
        if timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt, current_tz)

    return shift_name, shift_date, start_dt