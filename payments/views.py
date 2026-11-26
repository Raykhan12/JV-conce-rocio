import hashlib
import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from payments.models import Address, PaymentEvent
from payments.services.create_flow_payment import CreateFlowPayment
from payments.services.flow_client import FlowAPIError, FlowClient, FlowConfigurationError
from payments.services.process_flow_webhook import FlowWebhookProcessor


def _payload(request):
    if request.content_type == "application/json":
        try:
            return json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return {}
    return {key: request.POST.get(key) for key in request.POST}


@require_POST
@login_required
def create_flow_payment(request):
    data = _payload(request)
    try:
        address = Address.objects.get(pk=int(data.get("address_id")), user=request.user, active=True)
    except (TypeError, ValueError, Address.DoesNotExist):
        return JsonResponse({"ok": False, "error": "Dirección no encontrada."}, status=404)
    charge_ids = data.get("charge_ids") or request.POST.getlist("charge_ids")
    if isinstance(charge_ids, str):
        charge_ids = [value.strip() for value in charge_ids.split(",") if value.strip()]
    try:
        checkout_url, payment = CreateFlowPayment().call(
            address_id=address.pk,
            charge_ids=charge_ids,
            email=data.get("email", ""),
            name=data.get("name", ""),
            rut=data.get("rut", ""),
            user=request.user if request.user.is_authenticated else None,
        )
    except (TypeError, ValueError, KeyError) as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    except FlowAPIError:
        return JsonResponse({"ok": False, "error": "No fue posible iniciar el pago con Flow."}, status=502)
    except FlowConfigurationError:
        return JsonResponse({"ok": False, "error": "Pagos Flow no configurados."}, status=503)
    except ValidationError as exc:
        return JsonResponse({"ok": False, "error": exc.message if hasattr(exc, "message") else exc.messages[0]}, status=422)
    except (Address.DoesNotExist,):
        return JsonResponse({"ok": False, "error": "Dirección no encontrada."}, status=404)

    if request.content_type != "application/json":
        return redirect(checkout_url)

    return JsonResponse(
        {
            "ok": True,
            "payment_id": payment.pk,
            "checkout_url": checkout_url,
            "expires_at": payment.expires_at.isoformat() if payment.expires_at else None,
        },
        status=201,
    )


@login_required
@require_GET
def checkout(request):
    addresses = Address.objects.filter(user=request.user, active=True).order_by("label")
    address_id = request.GET.get("address")
    address = addresses.filter(pk=address_id).first() if address_id else addresses.first()
    charges = []
    if address:
        charges = address.charges.filter(status__in=["pending", "partial"]).order_by("due_date", "pk")
    return render(
        request,
        "payments/checkout.html",
        {
            "address": address,
            "addresses": addresses,
            "charges": charges,
        },
    )


@csrf_exempt
@require_POST
def flow_webhook(request):
    params = {key: request.POST.get(key) for key in request.POST}
    token = str(params.get("token", ""))
    if not token:
        fingerprint = hashlib.sha256(request.body).hexdigest()
        PaymentEvent.objects.get_or_create(
            external_id=f"invalid:{fingerprint}",
            defaults={
                "gateway": "flow",
                "event_type": "flow.invalid_signature",
                "payload": params,
                "processed": False,
            },
        )
        return JsonResponse({"ok": False, "error": "Missing token"}, status=401)

    try:
        flow = FlowClient(timeout=10)
    except FlowConfigurationError:
        return JsonResponse({"ok": False, "error": "Flow no configurado"}, status=503)

    # Flow Sandbox/Production confirmation callbacks may contain only `token`.
    # A present `s` is still verified; token-only callbacks are authenticated by
    # the processor's signed getStatus request against Flow.
    if params.get("s") and not flow.verify_webhook_signature(params):
        fingerprint = hashlib.sha256(json.dumps(params, sort_keys=True).encode("utf-8")).hexdigest()
        PaymentEvent.objects.get_or_create(
            external_id=f"invalid:{fingerprint}",
            defaults={
                "gateway": "flow",
                "event_type": "flow.invalid_signature",
                "payload": params,
                "processed": False,
            },
        )
        return JsonResponse({"ok": False, "error": "Invalid signature"}, status=401)

    try:
        result = FlowWebhookProcessor(flow).call(token=token, payload=params)
    except (FlowAPIError, ValueError):
        return JsonResponse({"ok": False, "error": "Flow unavailable"}, status=502)
    return JsonResponse(result, status=200)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def flow_return(request):
    token = str(request.GET.get("token") or request.POST.get("token") or "")
    state = "invalid"
    detail = "No se recibió un identificador de pago."
    payment_status = None
    if token:
        try:
            status_payload = FlowClient(timeout=10).get_status(token)
            flow_status = int(status_payload.get("status", 0))
            if flow_status == 2:
                state = "success"
                detail = "Pago confirmado. La plataforma registrará los abonos en tus cuotas."
            elif flow_status in (3, 4):
                state = "failed"
                detail = "El pago no fue aprobado o fue cancelado. Puedes iniciar un nuevo intento."
            else:
                state = "pending"
                detail = "Pago en proceso. La confirmación de Flow puede tardar algunos segundos."
        except (FlowAPIError, FlowConfigurationError, ValueError):
            state = "pending"
            detail = "Estamos esperando la confirmación segura de Flow. Puedes recargar esta página en unos segundos."

    if token:
        from payments.models import Payment

        payment = Payment.objects.filter(gateway_preference_id=token).only("status").first()
        payment_status = payment.status if payment else None
        if payment_status == Payment.Status.PAID:
            state = "success"
            detail = "Pago confirmado y aplicado a tus cuotas."

    return render(request, "payments/flow_return.html", {"state": state, "detail": detail})
