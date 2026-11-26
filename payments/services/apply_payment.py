import logging

from django.db import transaction
from django.utils import timezone

from payments.models import Charge, Payment, PaymentAllocation

logger = logging.getLogger(__name__)


def apply_payment_to_charges(payment, charge_ids=None):
    """Apply one Payment exactly once, locking Payment and Charge rows."""
    charge_ids = list(charge_ids or payment.metadata.get("charge_ids") or [])

    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if payment.status == Payment.Status.PAID and payment.allocations.exists():
            return payment

        charges = list(
            Charge.objects.select_for_update()
            .filter(
                address=payment.address,
                pk__in=charge_ids,
                status__in=[Charge.Status.PENDING, Charge.Status.PARTIAL],
            )
            .order_by("due_date", "pk")
        )

        unallocated = payment.amount_remaining
        for charge in charges:
            if unallocated <= 0:
                break
            amount_to_apply = min(unallocated, charge.remaining_amount)
            if amount_to_apply <= 0:
                continue
            PaymentAllocation.objects.create(
                payment=payment,
                charge=charge,
                amount=amount_to_apply,
            )
            charge.paid_amount += amount_to_apply
            charge.refresh_payment_status(save=False)
            charge.save(update_fields=["paid_amount", "status", "updated_at"])
            unallocated -= amount_to_apply

        if unallocated:
            payment.metadata = {**payment.metadata, "unallocated": unallocated}
            logger.warning(
                "Payment %s has %s CLP left after allocating to selected charges",
                payment.pk,
                unallocated,
            )
        payment.status = Payment.Status.PAID
        payment.paid_at = payment.paid_at or timezone.now()
        payment.save(update_fields=["status", "paid_at", "metadata", "updated_at"])
        return payment
