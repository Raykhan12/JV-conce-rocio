from django.db import transaction
from django.utils import timezone

from payments.models import Payment


def expire_pending_flow_payments(now=None):
    now = now or timezone.now()
    expired_ids = []
    with transaction.atomic():
        payments = Payment.objects.select_for_update(skip_locked=True).filter(
            gateway="flow",
            status__in=[Payment.Status.PENDING, Payment.Status.PROCESSING],
            expires_at__lte=now,
        )
        for payment in payments:
            payment.status = Payment.Status.EXPIRED
            payment.save(update_fields=["status", "updated_at"])
            expired_ids.append(payment.pk)
    return expired_ids
