import calendar
from datetime import date

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from payments.models import Charge, FeeConfig


def _next_period(year, month):
    month += 1
    return (year + 1, 1) if month == 13 else (year, month)


def _fee_for_period(year, month):
    period_date = date(year, month, 1)
    config = FeeConfig.objects.filter(valid_from__lte=period_date).filter(
        Q(valid_to__isnull=True) | Q(valid_to__gte=period_date)
    ).order_by("-valid_from").first()
    if config:
        return config.amount, config.due_day
    return (500 if year <= 2021 else 1000), 10


@transaction.atomic
def generate_missing_charges(address, through_date=None):
    """Materialize unpaid monthly charges after the latest paid period."""
    through_date = through_date or timezone.localdate()
    current_period = (through_date.year, through_date.month)
    latest_paid = (
        Charge.all_objects.filter(
            address=address,
            deleted_at__isnull=True,
            status=Charge.Status.PAID,
        )
        .order_by("-period_year", "-period_month")
        .first()
    )
    if latest_paid is None or (latest_paid.period_year, latest_paid.period_month) >= current_period:
        return []

    created = []
    period = _next_period(latest_paid.period_year, latest_paid.period_month)
    while period <= current_period:
        year, month = period
        if year not in (2020, 2021):
            if not Charge.all_objects.filter(
                address=address,
                period_year=year,
                period_month=month,
                deleted_at__isnull=True,
            ).exists():
                amount, due_day = _fee_for_period(year, month)
                due_day = min(due_day, calendar.monthrange(year, month)[1])
                due_date = date(year, month, due_day)
                charge, was_created = Charge.all_objects.get_or_create(
                    address=address,
                    period_year=year,
                    period_month=month,
                    defaults={
                        "amount": amount,
                        "due_date": due_date,
                        "status": Charge.Status.OVERDUE if due_date < through_date else Charge.Status.PENDING,
                    },
                )
                if was_created:
                    created.append(charge)
        period = _next_period(year, month)
    return created
