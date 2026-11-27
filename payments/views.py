import hashlib
import json
import re
import unicodedata
from difflib import SequenceMatcher

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods

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


def _address_key(value):
    normalized = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().lower()
    normalized = re.sub(r"\b0+(\d+)\b", r"\1", normalized)
    return "".join(character for character in normalized if character.isalnum())


def _address_words(value):
    return [word for word in re.split(r"[^a-z0-9]+", _address_key_words(value)) if word]


def _address_key_words(value):
    normalized = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\b0+(\d+)\b", r"\1", normalized)


def _address_match_score(address_label, query):
    label_words = _address_words(address_label)
    query_words = _address_words(query)
    if not query_words:
        return 0
    label_blob = " ".join(label_words)
    query_blob = " ".join(query_words)
    exact_key = _address_key(address_label) == _address_key(query)
    contains_all = all(word in label_words or any(word in item for item in label_words) for word in query_words)
    matched_words = sum(any(word in item for item in label_words) for word in query_words)
    ratio = SequenceMatcher(None, _address_key(query), _address_key(address_label)).ratio()
    if exact_key:
        return 100
    if contains_all:
        return 80 + (matched_words / len(query_words)) * 10 - min(len(label_blob) - len(query_blob), 30) / 100
    if ratio >= 0.62:
        return ratio * 70 + matched_words * 2
    return 0


def _payment_error(request, message, status):
    if request.content_type == "application/json":
        return JsonResponse({"ok": False, "error": message}, status=status)
    messages.error(request, message)
    return redirect("payments:checkout")


@require_POST
def create_flow_payment(request):
    data = _payload(request)
    address_id = request.session.get("payment_address_id")
    try:
        address = Address.objects.get(pk=int(address_id), active=True)
    except (TypeError, ValueError, Address.DoesNotExist):
        owned_address_id = data.get("address_id")
        address = None
        if request.user.is_authenticated:
            address = Address.objects.filter(pk=owned_address_id, user=request.user, active=True).first()
        if address is None:
            return _payment_error(request, "Busca primero tu dirección.", 403)

    if str(data.get("address_id", "")) != str(address.pk):
        return _payment_error(request, "La dirección seleccionada no coincide con la consulta.", 403)

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
            payment_amount=data.get("payment_amount"),
            user=request.user if request.user.is_authenticated else None,
        )
    except (TypeError, ValueError, KeyError) as exc:
        return _payment_error(request, str(exc), 400)
    except FlowAPIError:
        return _payment_error(request, "No fue posible iniciar el pago con Flow.", 502)
    except FlowConfigurationError:
        return _payment_error(request, "Pagos Flow no configurados.", 503)
    except ValidationError as exc:
        message = exc.message if hasattr(exc, "message") else exc.messages[0]
        return _payment_error(request, message, 422)
    except Address.DoesNotExist:
        return _payment_error(request, "Dirección no encontrada.", 404)

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


@require_http_methods(["GET", "POST"])
def checkout(request):
    lookup_error = ""
    if request.GET.get("cambiar") == "1":
        request.session.pop("payment_address_id", None)
        return redirect("payments:checkout")
    if request.method == "POST":
        address_text = " ".join(request.POST.get("address", "").strip().split())
        selected_address_id = request.POST.get("address_id", "").strip()
        if not address_text:
            lookup_error = "Ingresa la dirección completa de tu hogar."
        else:
            selected = Address.objects.filter(pk=selected_address_id, active=True).first() if selected_address_id.isdigit() else None
            if selected and _address_key(selected.label) != _address_key(address_text):
                selected = None
            address_key = _address_key(address_text)
            matches = [
                item
                for item in Address.objects.filter(active=True).only("pk", "label")
                if _address_key(item.label) == address_key
            ]
            if selected:
                request.session["payment_address_id"] = selected.pk
                return redirect("payments:checkout")
            if len(matches) == 1:
                request.session["payment_address_id"] = matches[0].pk
                return redirect("payments:checkout")
            if len(matches) > 1:
                lookup_error = "Hay más de un registro con esa dirección. Contacta a Tesorería para resolverlo."
            else:
                lookup_error = "Selecciona tu dirección de la lista de sugerencias o revisa cómo está escrita."

    addresses = Address.objects.none()
    if request.user.is_authenticated:
        addresses = Address.objects.filter(user=request.user, active=True).order_by("label")
        requested_address = request.GET.get("address")
        if requested_address and addresses.filter(pk=requested_address).exists():
            request.session["payment_address_id"] = int(requested_address)

    address = None
    session_address_id = request.session.get("payment_address_id")
    if session_address_id:
        address = Address.objects.filter(pk=session_address_id, active=True).first()
    elif addresses:
        address = addresses.first()
        request.session["payment_address_id"] = address.pk

    charges = []
    if address:
        charges = address.charges.filter(status__in=["pending", "partial", "overdue"]).order_by("due_date", "pk")

    return render(
        request,
        "payments/checkout.html",
        {"address": address, "addresses": addresses, "charges": charges, "lookup_error": lookup_error},
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


def address_suggestions(request):
    query = " ".join(request.GET.get("q", "").strip().split())
    if len(_address_key(query)) < 2:
        return JsonResponse({"results": []})
    matches = []
    for address in Address.objects.filter(active=True).only("pk", "label"):
        score = _address_match_score(address.label, query)
        if score:
            matches.append((score, address))
    matches.sort(key=lambda item: (-item[0], item[1].label))
    return JsonResponse({
        "results": [{"id": address.pk, "label": address.label} for _, address in matches[:8]],
    })
