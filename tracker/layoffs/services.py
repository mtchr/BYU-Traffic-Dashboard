"""Shared layoff writes using the project's current Denver convention."""

from datetime import datetime, time, timedelta
import re

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from tracker.lot_polygons import CAMPUS_LOTS
from tracker.models import Layoff, Lot


PERMISSION_MESSAGE = 'You lack permissions to alter lots.'
SPECIAL_LOTS = {'Lot B67', 'CFA', 'MCD', 'CANES'}
WINDOW_FIELDS = {
    'business_date', 'all_day', 'start', 'end', 'lot_id',
}


class LayoffConflict(Exception):
    """The caller's record or requested action is no longer current."""


def can_manage_layoffs(user):
    return (
        user.is_authenticated
        and user.has_perm('tracker.manage_layoffs')
    )


def _require_manager(user):
    if not can_manage_layoffs(user):
        raise PermissionDenied(PERMISSION_MESSAGE)


def _check_fields(payload, allowed):
    if not isinstance(payload, dict):
        raise ValidationError('Send a JSON object.')

    unknown = set(payload) - allowed
    if unknown:
        raise ValidationError(
            'Unknown fields: ' + ', '.join(sorted(unknown))
        )


def _positive_integer(value, field):
    if type(value) is not int or value < 1:
        raise ValidationError({field: 'Use a positive integer.'})
    return value


def _check_day(payload, now):
    if payload.get('business_date') != now.date().isoformat():
        raise ValidationError({
            'business_date': (
                'Layoffs can only be changed for today. '
                'Refresh the form.'
            )
        })


def lot_is_eligible(lot):
    return (
        lot.name in CAMPUS_LOTS
        and lot.name not in SPECIAL_LOTS
        and not lot.is_static_icon
    )


def _require_eligible(lot):
    if not lot_is_eligible(lot):
        raise ValidationError({
            'lot_id': 'This location does not support layoffs.'
        })


def _clock(value, field, now):
    if (
        not isinstance(value, str)
        or not re.fullmatch(r'\d{2}:\d{2}', value)
    ):
        raise ValidationError({
            field: 'Use a time in HH:MM format.'
        })

    try:
        selected = datetime.strptime(value, '%H:%M').time()
    except ValueError:
        raise ValidationError({field: 'Choose a valid time.'})

    return datetime.combine(now.date(), selected)


def _window(payload, now):
    _check_day(payload, now)

    all_day = payload.get('all_day')
    if type(all_day) is not bool:
        raise ValidationError({
            'all_day': 'Choose All Day or a timed window.'
        })

    midnight = datetime.combine(
        now.date() + timedelta(days=1), time.min
    )
    start_value = payload.get('start', 'now')
    end_value = payload.get('end', 'midnight')

    if all_day:
        if start_value != 'now' or end_value != 'midnight':
            raise ValidationError(
                'All Day begins now and ends at midnight.'
            )
        return now, midnight, True

    start = (
        now if start_value == 'now'
        else _clock(start_value, 'start', now)
    )
    end = (
        midnight if end_value == 'midnight'
        else _clock(end_value, 'end', now)
    )

    if start < now:
        raise ValidationError({
            'start': 'A layoff cannot be backdated. Choose Now.'
        })
    if end <= start:
        raise ValidationError({'end': 'End must be after start.'})

    return start, end, False


def effective_end(layoff):
    if layoff.cancelled_at is not None:
        return max(
            layoff.starts_at,
            min(layoff.ends_at, layoff.cancelled_at),
        )
    return layoff.ends_at


def _check_overlap(lot, start, end, exclude_id=None):
    candidates = Layoff.objects.filter(
        lot=lot,
        starts_at__lt=end,
        ends_at__gt=start,
    )
    if exclude_id is not None:
        candidates = candidates.exclude(pk=exclude_id)

    for other in candidates:
        if effective_end(other) > max(start, other.starts_at):
            raise ValidationError({
                'start': (
                    'This lot already has an overlapping layoff.'
                )
            })


def _lock_record(layoff_id, payload):
    lot_id = Layoff.objects.values_list(
        'lot_id', flat=True
    ).get(pk=layoff_id)

    Lot.objects.select_for_update().get(pk=lot_id)
    record = (
        Layoff.objects.select_for_update()
        .select_related('lot')
        .get(pk=layoff_id)
    )

    version = _positive_integer(
        payload.get('version'), 'version'
    )
    if record.version != version:
        raise LayoffConflict(
            'This layoff changed. Refresh before saving again.'
        )

    return record


def _check_editable(record, payload, now):
    _check_day(payload, now)

    if record.cancelled_at is not None:
        raise LayoffConflict(
            'This layoff has already been cancelled or replaced.'
        )
    if now >= record.ends_at:
        raise LayoffConflict('This layoff has already ended.')


def _cancel(record, actor, now):
    record.cancelled_at = now
    record.cancelled_by = actor
    record.version += 1
    record.full_clean()
    record.save(
        update_fields=['cancelled_at', 'cancelled_by', 'version']
    )


@transaction.atomic
def create_layoff(*, actor, payload):
    _require_manager(actor)
    _check_fields(payload, WINDOW_FIELDS)

    lot_id = _positive_integer(
        payload.get('lot_id'), 'lot_id'
    )
    lot = Lot.objects.select_for_update().get(pk=lot_id)
    _require_eligible(lot)

    start, end, all_day = _window(payload, timezone.now())
    _check_overlap(lot, start, end)

    record = Layoff(
        lot=lot,
        starts_at=start,
        ends_at=end,
        all_day=all_day,
        created_by=actor,
    )
    record.full_clean()
    record.save()
    return record


@transaction.atomic
def cancel_layoff(*, actor, layoff_id, payload):
    _require_manager(actor)
    _check_fields(payload, {'business_date', 'version'})

    record = _lock_record(layoff_id, payload)
    now = timezone.now()
    _check_editable(record, payload, now)
    _cancel(record, actor, now)
    return record


@transaction.atomic
def replace_layoff(*, actor, layoff_id, payload):
    _require_manager(actor)
    _check_fields(payload, WINDOW_FIELDS | {'version'})

    record = _lock_record(layoff_id, payload)
    now = timezone.now()
    _check_editable(record, payload, now)
    _require_eligible(record.lot)

    if (
        'lot_id' in payload
        and _positive_integer(payload['lot_id'], 'lot_id')
        != record.lot_id
    ):
        raise ValidationError({
            'lot_id': 'A layoff cannot be moved to another lot.'
        })

    start, end, all_day = _window(payload, now)
    _check_overlap(
        record.lot, start, end, exclude_id=record.pk
    )

    replacement = Layoff(
        lot=record.lot,
        starts_at=start,
        ends_at=end,
        all_day=all_day,
        created_by=actor,
        replaces=record,
    )
    replacement.full_clean()

    _cancel(record, actor, now)
    replacement.save()
    return replacement