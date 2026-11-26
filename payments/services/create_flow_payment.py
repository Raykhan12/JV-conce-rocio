from datetime import timedelta
from urllib.parse import urljoin
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from payments.models import Address, Charge, Payment
from payments.services.flow_client import FlowClient


class CreateFlowPayment:
    def __init__(self, flow_client=None):
        self.flow = flow_client or FlowClient()

    @staticmethod
    def absolute_url(path):
        return urljoin(settings.SITE_URL.rstrip("/") + "/", path.lstrip("/"))

    def call(self, *, address_id, charge_ids, email, name="", rut="", user=None):
        charge_ids = list(dict.fromkeys(int(value) for value in charge_ids if str(value).isdigit()))
        if not charge_ids:
            raise ValidationError("Debes seleccionar al menos un cargo.")

        expires_at = timezone.now() + timedelta(seconds=int(getattr(settings, "FLOW_PAYMENT_TIMEOUT", 1800)))
        with transaction.atomic():
            address = Address.objects.select_for_update().get(pk=address_id)
            charges = list(
                Charge.objects.select_for_update()
                .filter(
                    pk__in=charge_ids,
                    address=address,
                    status__in=[Charge.Status.PENDING, Charge.Status.PARTIAL],
                )
                .order_by("due_date", "pk")
            )
            if {charge.pk for charge in charges} != set(charge_ids):
                raise ValidationError("Uno o más cargos no existen, no pertenecen a la dirección o no están pendientes.")
            remaining_by_id = {charge.pk: charge.remaining_amount for charge in charges}
            if any(value <= 0 for value in remaining_by_id.values()):
                raise ValidationError("Uno de los cargos seleccionados ya fue pagado.")
            total = sum(remaining_by_id.values())
            payment = Payment.objects.create(
                address=address,
                user=user,
                amount=total,
                currency="CLP",
                status=Payment.Status.PENDING,
                source="online",
                payment_method="flow",
                gateway="flow",
                payer_email=email,
                payer_name=name,
                payer_rut=rut,
                description=f"Cuotas JJVV Villa Concepción-El Rocío ({len(charges)} cargos)",
                metadata={
                    "charge_ids": [charge.pk for charge in charges],
                    "charge_remaining_amounts": remaining_by_id,
                },
                expires_at=expires_at,
            )
            commerce_order = f"JJVV-{payment.pk}-{uuid4().hex[:8]}"
            order = self.flow.create_payment(
                commerce_order=commerce_order,
                subject=payment.description,
                amount=payment.amount,
                email=payment.payer_email,
                url_confirmation=settings.FLOW_CONFIRMATION_URL or self.absolute_url(reverse("payments:flow_webhook")),
                url_return=settings.FLOW_RETURN_URL or self.absolute_url(reverse("payments:flow_return")),
                optional={"payment_id": payment.pk, "address_id": address.pk},
                timeout=int(getattr(settings, "FLOW_PAYMENT_TIMEOUT", 1800)),
            )
            payment.gateway_payment_id = str(order["flow_order"])
            payment.gateway_preference_id = str(order["token"])
            payment.metadata["commerce_order"] = commerce_order
            payment.metadata["flow_order"] = str(order["flow_order"])
            payment.save(update_fields=["gateway_payment_id", "gateway_preference_id", "metadata", "updated_at"])
            return order["payment_url"], payment


def create_flow_payment(address, charge_ids, payer_email, payer_name="", payer_rut=None, user=None):
    checkout_url, payment = CreateFlowPayment().call(
        address_id=address.pk if hasattr(address, "pk") else address,
        charge_ids=charge_ids,
        email=payer_email,
        name=payer_name,
        rut=payer_rut or "",
        user=user,
    )
    return {"payment": payment, "payment_url": checkout_url}
