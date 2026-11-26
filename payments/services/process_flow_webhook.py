from django.db import transaction
from django.utils import timezone

from payments.models import Charge, Payment, PaymentEvent
from payments.services.flow_client import FlowClient


class FlowWebhookProcessor:
    EVENT_TYPE = "flow.payment_confirmation"

    def __init__(self, flow_client=None):
        self.flow = flow_client or FlowClient()

    @classmethod
    def event_external_id(cls, token):
        return f"{token}:confirmation"

    def call(self, *, token, payload):
        external_id = self.event_external_id(token)
        event, _ = PaymentEvent.objects.get_or_create(
            external_id=external_id,
            defaults={"gateway": "flow", "event_type": self.EVENT_TYPE, "payload": payload},
        )
        if event.processed:
            return {"ok": True, "idempotent": True}

        payment = Payment.objects.filter(gateway_preference_id=token, gateway="flow").first()
        if payment is None:
            return {"ok": True, "payment_found": False}

        status_payload = self.flow.get_status(token)
        status = int(status_payload.get("status", 0))

        if status == 1:
            return {"ok": True, "payment_status": Payment.Status.PENDING}

        if status in (3, 4):
            with transaction.atomic():
                locked_event = PaymentEvent.objects.select_for_update().get(pk=event.pk)
                if locked_event.processed:
                    return {"ok": True, "idempotent": True}
                locked_payment = Payment.objects.select_for_update().get(pk=payment.pk)
                if locked_event.payment_id is None:
                    locked_event.payment = locked_payment
                locked_payment.status = Payment.Status.FAILED if status == 3 else Payment.Status.CANCELLED
                locked_payment.metadata = {
                    **locked_payment.metadata,
                    "flow_status": status_payload,
                }
                locked_payment.save(update_fields=["status", "metadata", "updated_at"])
                locked_event.processed = True
                locked_event.processed_at = timezone.now()
                locked_event.payload = payload
                locked_event.save(update_fields=["processed", "processed_at", "payload", "payment"])
            return {"ok": True, "payment_status": locked_payment.status}

        if status != 2:
            return {"ok": True, "payment_status": "unknown"}

        with transaction.atomic():
            locked_event = PaymentEvent.objects.select_for_update().get(pk=event.pk)
            if locked_event.processed:
                return {"ok": True, "idempotent": True}

            locked_payment = Payment.objects.select_for_update().select_related("address").get(pk=payment.pk)
            if locked_event.payment_id is None:
                locked_event.payment = locked_payment
            if locked_payment.status != Payment.Status.PAID:
                locked_payment.apply_to_charges(locked_payment.metadata.get("charge_ids", []))
                locked_payment.refresh_from_db()
                locked_payment.metadata = {**locked_payment.metadata, "flow_status": status_payload}
                locked_payment.save(update_fields=["metadata", "updated_at"])
                self.generate_receipt_if_available(locked_payment)

            locked_event.processed = True
            locked_event.processed_at = timezone.now()
            locked_event.payload = payload
            locked_event.save(update_fields=["payment", "processed", "processed_at", "payload"])
            return {"ok": True, "payment_status": locked_payment.status}

    @staticmethod
    def generate_receipt_if_available(payment):
        # Hook intencional: cuando exista Receipt, generar el comprobante aquí
        # después de committed; por ahora no hay modelo ni dependencia de PDF.
        return None
