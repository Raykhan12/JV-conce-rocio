from django.db.models import OuterRef, Subquery
from django.utils import timezone

from payments.models import Address, Charge, FeeConfig


MONTH_NAMES = (
    'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
)


def _next_period(year, month):
    month += 1
    return (year + 1, 1) if month == 13 else (year, month)


def _inferred_fee(fee_configs, year, month):
    period_date = timezone.datetime(year, month, 1).date()
    for config in fee_configs:
        if config.valid_from <= period_date and (config.valid_to is None or period_date <= config.valid_to):
            return config.amount
    return 500 if year <= 2021 else 1000


def debt_status_by_address():
    charges = Charge.all_objects.filter(deleted_at__isnull=True)
    last_paid_charges = charges.filter(
        address_id=OuterRef('pk'),
        status=Charge.Status.PAID,
    ).order_by('-period_year', '-period_month')
    current_date = timezone.localdate()
    current_period = (current_date.year, current_date.month)
    fee_configs = list(FeeConfig.objects.order_by('-valid_from'))
    address_charges = {}
    for charge in charges.values('address_id', 'period_year', 'period_month', 'status', 'amount', 'paid_amount'):
        address_charges.setdefault(charge['address_id'], {})[(charge['period_year'], charge['period_month'])] = charge

    addresses = list(
        Address.objects.filter(active=True)
        .annotate(
            last_paid_year=Subquery(last_paid_charges.values('period_year')[:1]),
            last_paid_month=Subquery(last_paid_charges.values('period_month')[:1]),
        )
        .order_by('label')
    )
    for address in addresses:
        period_charges = address_charges.get(address.pk, {})
        registered_debt = [
            charge for (year, month), charge in period_charges.items()
            if (year, month) <= current_period
            and year not in (2020, 2021)
            and charge['status'] in [Charge.Status.PENDING, Charge.Status.PARTIAL, Charge.Status.OVERDUE]
            and charge['amount'] > charge['paid_amount']
        ]
        address.debt_count = len(registered_debt)
        address.debt_amount = sum(charge['amount'] - charge['paid_amount'] for charge in registered_debt)
        first_missing_period = None

        if address.last_paid_year and address.last_paid_month:
            address.last_paid_label = f'{MONTH_NAMES[address.last_paid_month - 1]} {address.last_paid_year}'
            paid_period = (address.last_paid_year, address.last_paid_month)
            if paid_period < current_period:
                period = _next_period(*paid_period)
                while period <= current_period:
                    existing = period_charges.get(period)
                    if period[0] not in (2020, 2021) and existing is None:
                        address.debt_count += 1
                        address.debt_amount += _inferred_fee(fee_configs, *period)
                        first_missing_period = first_missing_period or period
                    period = _next_period(*period)

            if address.debt_amount:
                start_year, start_month = first_missing_period or min(
                    (charge_period for charge_period, charge in period_charges.items()
                     if charge['status'] in [Charge.Status.PENDING, Charge.Status.PARTIAL, Charge.Status.OVERDUE]
                     and charge_period <= current_period
                     and charge_period[0] not in (2020, 2021)),
                    default=_next_period(*paid_period),
                )
                address.payment_state = f'Pendiente desde {MONTH_NAMES[start_month - 1]} {start_year}'
                address.payment_state_key = 'debt'
                address.payment_state_class = 'is-red'
            elif paid_period == current_period:
                address.payment_state = 'Al día'
                address.payment_state_key = 'current'
                address.payment_state_class = 'is-green'
            else:
                address.payment_state = 'Pago adelantado registrado'
                address.payment_state_key = 'advance'
                address.payment_state_class = 'is-amber'
        elif address.debt_amount:
            address.last_paid_label = 'Sin cuota pagada'
            address.payment_state = 'Tiene cuotas pendientes'
            address.payment_state_key = 'debt'
            address.payment_state_class = 'is-red'
        else:
            address.last_paid_label = 'Sin cuota pagada'
            address.payment_state = 'Revisar domicilio'
            address.payment_state_key = 'review'
            address.payment_state_class = 'is-red'

    return addresses


def debt_periods_for_address(address):
    through_date = timezone.localdate()
    current_period = (through_date.year, through_date.month)
    charges = list(
        Charge.all_objects.filter(address=address, deleted_at__isnull=True)
        .order_by('period_year', 'period_month')
    )
    by_period = {(charge.period_year, charge.period_month): charge for charge in charges}
    last_paid = next((charge for charge in reversed(charges) if charge.status == Charge.Status.PAID), None)
    periods = []

    for charge in charges:
        period = (charge.period_year, charge.period_month)
        if period <= current_period and period[0] not in (2020, 2021):
            if charge.status in [Charge.Status.PENDING, Charge.Status.PARTIAL, Charge.Status.OVERDUE] and charge.remaining_amount > 0:
                periods.append({
                    'year': charge.period_year,
                    'month': charge.period_month,
                    'amount': charge.remaining_amount,
                    'kind': 'Registrada',
                })

    if last_paid and (last_paid.period_year, last_paid.period_month) < current_period:
        fee_configs = list(FeeConfig.objects.order_by('-valid_from'))
        period = _next_period(last_paid.period_year, last_paid.period_month)
        registered = {(item['year'], item['month']) for item in periods}
        while period <= current_period:
            existing = by_period.get(period)
            if period[0] not in (2020, 2021) and existing is None and period not in registered:
                periods.append({
                    'year': period[0],
                    'month': period[1],
                    'amount': _inferred_fee(fee_configs, *period),
                    'kind': 'Calculada',
                })
            period = _next_period(*period)

    return sorted(periods, key=lambda item: (item['year'], item['month']))
