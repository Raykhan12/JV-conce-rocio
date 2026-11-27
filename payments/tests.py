import hashlib
import hmac
import time
from datetime import timedelta, date
from threading import Barrier, Thread
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from payments.models import Address, Charge, Payment, PaymentAllocation, PaymentEvent
from payments.services.create_flow_payment import CreateFlowPayment
from payments.services.flow_client import FlowClient
from payments.services.process_flow_webhook import FlowWebhookProcessor


def signed(params, secret="test-secret"):
    base = {key: str(value) for key, value in params.items() if key != "s"}
    payload = "".join(f"{key}{base[key]}" for key in sorted(base))
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


class FakeFlowClient:
    def __init__(self, token="token-test", flow_order="12345"):
        self.token = token
        self.flow_order = flow_order
        self.created = None

    def create_payment(self, **kwargs):
        self.created = kwargs
        return {
            "flow_order": self.flow_order,
            "token": self.token,
            "payment_url": f"https://sandbox.flow.cl/app/web/pay.php?token={self.token}",
            "raw": {"flowOrder": self.flow_order, "token": self.token},
        }


class FlowClientSignatureTests(TestCase):
    def test_signature_is_hmac_sha256_sorted_by_parameter_name(self):
        params = {"subject": "Cuota 2026-11", "amount": 12500, "apiKey": "abc", "email": "vecino@example.cl"}
        expected = signed(params)
        self.assertEqual(FlowClient.signature_for(params, "test-secret"), expected)
        self.assertTrue(
            hmac.compare_digest(
                FlowClient.signature_for({**params, "s": expected, "token": "ignored"}, "test-secret"),
                signed({**params, "token": "ignored"}),
            )
        )

    def test_verify_signature_rejects_tampering(self):
        params = {"token": "abc123", "s": signed({"token": "abc123"})}
        client = FlowClient(api_key="api", secret_key="test-secret")
        self.assertTrue(client.verify_webhook_signature(params))
        self.assertFalse(client.verify_webhook_signature({**params, "token": "changed"}))
        self.assertFalse(client.verify_webhook_signature({**params, "s": "bad"}))

    @patch("payments.services.flow_client.requests.request")
    def test_create_payment_posts_signed_form_and_builds_checkout_url(self, request_mock):
        request_mock.return_value.json.return_value = {
            "flowOrder": 77,
            "token": "checkout-token",
            "url": "https://sandbox.flow.cl/app/web/pay.php",
        }
        client = FlowClient(api_key="api", secret_key="test-secret")

        order = client.create_payment(
            commerce_order="JV-1",
            subject="Cuotas",
            amount=10000,
            email="vecino@example.cl",
            url_confirmation="https://site.cl/webhooks/flow/",
            url_return="https://site.cl/payments/flow/return/",
            optional={"payment_id": 1},
        )

        method, url = request_mock.call_args.args[:2]
        form = request_mock.call_args.kwargs["data"]
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith("/payment/create"))
        self.assertEqual(form["apiKey"], "api")
        self.assertRegex(form["s"], r"^[0-9a-f]{64}$")
        self.assertEqual(order["payment_url"], "https://sandbox.flow.cl/app/web/pay.php?token=checkout-token")


class FlowPaymentTests(TestCase):
    def setUp(self):
        self.address = Address.objects.create(label="Pasaje Central 123", owner_email="vecino@example.cl")
        self.one = Charge.objects.create(
            address=self.address,
            period_year=2026,
            period_month=1,
            amount=10000,
            due_date=timezone.localdate() - timedelta(days=20),
        )
        self.two = Charge.objects.create(
            address=self.address,
            period_year=2026,
            period_month=2,
            amount=12500,
            due_date=timezone.localdate() - timedelta(days=5),
        )

    @override_settings(FLOW_API_KEY="api-test", FLOW_SECRET_KEY="secret-test")
    def test_creates_payment_for_multiple_charges_and_allocates_after_webhook(self):
        flow = FakeFlowClient()
        checkout_url, payment = CreateFlowPayment(flow).call(
            address_id=self.address.pk,
            charge_ids=[self.one.pk, self.two.pk],
            email="vecino@example.cl",
            name="Vecino Prueba",
            rut="12.345.678-9",
        )
        self.assertEqual(payment.amount, 22500)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.gateway_preference_id, "token-test")
        self.assertEqual(payment.metadata["charge_ids"], [self.one.pk, self.two.pk])
        self.assertEqual(payment.allocations.count(), 0)
        self.assertIn("token=token-test", checkout_url)

        flow.status_result = {"status": 2, "flowOrder": 12345}
        flow.get_status = lambda token: flow.status_result
        FlowWebhookProcessor(flow).call(token="token-test", payload={"token": "token-test"})

        payment.refresh_from_db()
        self.one.refresh_from_db()
        self.two.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.allocations.count(), 2)
        self.assertEqual(self.one.status, Charge.Status.PAID)
        self.assertEqual(self.two.status, Charge.Status.PAID)
        self.assertEqual(sum(payment.allocations.values_list("amount", flat=True)), 22500)

    @override_settings(FLOW_API_KEY="api-test", FLOW_SECRET_KEY="secret-test")
    def test_creates_partial_payment_for_selected_debt(self):
        flow = FakeFlowClient()
        _url, payment = CreateFlowPayment(flow).call(
            address_id=self.address.pk,
            charge_ids=[self.one.pk, self.two.pk],
            email="vecino@example.cl",
            payment_amount=4000,
        )

        self.assertEqual(payment.amount, 4000)
        self.assertEqual(flow.created["amount"], 4000)
        self.assertEqual(payment.metadata["charge_ids"], [self.one.pk, self.two.pk])

    def test_rejects_charge_from_another_address_or_already_paid(self):
        other = Address.objects.create(label="Pasaje Sur 55")
        other_charge = Charge.objects.create(
            address=other,
            period_year=2026,
            period_month=1,
            amount=10000,
            due_date=timezone.localdate(),
        )
        with self.assertRaises(ValidationError):
            CreateFlowPayment(FakeFlowClient()).call(
                address_id=self.address.pk,
                charge_ids=[self.one.pk, other_charge.pk],
                email="vecino@example.cl",
            )

        self.one.status = Charge.Status.PAID
        self.one.paid_amount = self.one.amount
        self.one.save(update_fields=["status", "paid_amount"])
        with self.assertRaises(ValidationError):
            CreateFlowPayment(FakeFlowClient()).call(
                address_id=self.address.pk,
                charge_ids=[self.one.pk],
                email="vecino@example.cl",
            )

    def test_partial_payment_leaves_partial_status_without_overallocation(self):
        payment = Payment.objects.create(
            address=self.address,
            amount=4000,
            payer_email="vecino@example.cl",
            gateway="flow",
            status=Payment.Status.PENDING,
            gateway_preference_id="partial-token",
            metadata={"charge_ids": [self.one.pk]},
        )
        flow = FakeFlowClient(token="partial-token")
        flow.get_status = lambda token: {"status": 2}
        FlowWebhookProcessor(flow).call(token="partial-token", payload={"token": "partial-token"})
        self.one.refresh_from_db()
        self.assertEqual(self.one.paid_amount, 4000)
        self.assertEqual(self.one.status, Charge.Status.PARTIAL)
        self.assertEqual(PaymentAllocation.objects.get(payment=payment).amount, 4000)

    def test_same_webhook_twice_is_idempotent(self):
        payment = Payment.objects.create(
            address=self.address,
            amount=self.one.amount,
            payer_email="vecino@example.cl",
            gateway="flow",
            gateway_preference_id="idem-token",
            metadata={"charge_ids": [self.one.pk]},
        )
        flow = FakeFlowClient(token="idem-token")
        flow.get_status = lambda token: {"status": 2}
        processor = FlowWebhookProcessor(flow)
        first = processor.call(token="idem-token", payload={"token": "idem-token"})
        second = processor.call(token="idem-token", payload={"token": "idem-token"})
        self.assertTrue(first["ok"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(PaymentAllocation.objects.filter(payment=payment, charge=self.one).count(), 1)
        self.one.refresh_from_db()
        self.assertEqual(self.one.paid_amount, self.one.amount)

    def test_checkout_materializes_missing_months_and_excludes_waived_years(self):
        historical = Address.objects.create(label="Alborada Prueba 82")
        Charge.objects.create(
            address=historical,
            period_year=2019,
            period_month=12,
            amount=1000,
            paid_amount=1000,
            status=Charge.Status.PAID,
            due_date=date(2019, 12, 10),
        )

        from payments.services.generate_address_charges import generate_missing_charges

        generated = generate_missing_charges(historical, through_date=date(2022, 3, 31))

        self.assertEqual(
            [(item.period_year, item.period_month, item.amount) for item in generated],
            [(2022, 1, 1000), (2022, 2, 1000), (2022, 3, 1000)],
        )
        self.assertFalse(Charge.all_objects.filter(address=historical, period_year__in=[2020, 2021]).exists())


@override_settings(SECURE_SSL_REDIRECT=False)
class FlowWebhookViewTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.address = Address.objects.create(label="Los Aromos 42")
        self.charge = Charge.objects.create(
            address=self.address,
            period_year=2026,
            period_month=11,
            amount=5000,
            due_date=timezone.localdate(),
        )
        self.payment = Payment.objects.create(
            address=self.address,
            amount=5000,
            payer_email="vecino@example.cl",
            gateway="flow",
            gateway_preference_id="webhook-token",
            metadata={"charge_ids": [self.charge.pk]},
        )

    @override_settings(FLOW_API_KEY="api-test", FLOW_SECRET_KEY="test-secret")
    def test_invalid_signature_returns_401_and_records_unprocessed_event(self):
        response = self.client.post(
            reverse("payments:flow_webhook"),
            {"token": "webhook-token", "s": "invalid"},
        )
        self.assertEqual(response.status_code, 401)
        event = PaymentEvent.objects.get(event_type="flow.invalid_signature")
        self.assertFalse(event.processed)
        self.assertEqual(event.payload["token"], "webhook-token")

    @override_settings(FLOW_API_KEY="api-test", FLOW_SECRET_KEY="test-secret")
    @patch("payments.views.FlowClient.get_status", return_value={"status": 2, "flowOrder": 901})
    def test_token_only_webhook_is_authorized_by_get_status(self, get_status):
        response = self.client.post(
            reverse("payments:flow_webhook"),
            {"token": "webhook-token"},
        )

        self.assertEqual(response.status_code, 200)
        get_status.assert_called_once_with("webhook-token")
        self.assertEqual(PaymentAllocation.objects.filter(payment=self.payment).count(), 1)
        self.assertTrue(PaymentEvent.objects.get(external_id="webhook-token:confirmation").processed)

    @override_settings(FLOW_API_KEY="api-test", FLOW_SECRET_KEY="test-secret")
    @patch("payments.views.FlowClient.get_status", return_value={"status": 2, "flowOrder": 901})
    def test_flow_return_accepts_post_but_does_not_allocate_payment(self, get_status):
        response = self.client.post(
            reverse("payments:flow_return"),
            {"token": "webhook-token"},
        )

        self.assertEqual(response.status_code, 200)
        get_status.assert_called_once_with("webhook-token")
        self.assertEqual(PaymentAllocation.objects.filter(payment=self.payment).count(), 0)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    @override_settings(FLOW_API_KEY="api-test", FLOW_SECRET_KEY="test-secret")
    @patch("payments.views.FlowClient.get_status", return_value={"status": 2, "flowOrder": 900})
    def test_valid_webhook_returns_200_in_under_15_seconds_and_is_idempotent(self, _get_status):
        payload = {"token": "webhook-token"}
        payload["s"] = signed(payload)
        started = time.monotonic()
        first = self.client.post(reverse("payments:flow_webhook"), payload)
        elapsed = time.monotonic() - started
        second = self.client.post(reverse("payments:flow_webhook"), payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertLess(elapsed, 15)
        self.assertEqual(PaymentAllocation.objects.filter(payment=self.payment).count(), 1)
        self.assertTrue(PaymentEvent.objects.get(external_id="webhook-token:confirmation").processed)

    @override_settings(FLOW_API_KEY="api-test", FLOW_SECRET_KEY="test-secret")
    @patch("payments.views.FlowClient.get_status")
    def test_unknown_payment_returns_200_without_calling_flow(self, get_status):
        payload = {"token": "unknown-token"}
        payload["s"] = signed(payload)
        response = self.client.post(reverse("payments:flow_webhook"), payload)
        self.assertEqual(response.status_code, 200)
        get_status.assert_not_called()
        event = PaymentEvent.objects.get(external_id="unknown-token:confirmation")
        self.assertFalse(event.processed)
        self.assertIsNone(event.payment)


class FlowExpirationTests(TestCase):
    def test_expire_pending_flow_payments_only_marks_expired_items(self):
        from payments.expiration import expire_pending_flow_payments

        address = Address.objects.create(label="Pasaje Expiración 10")
        expired = Payment.objects.create(
            address=address,
            amount=5000,
            payer_email="vecino@example.cl",
            gateway="flow",
            status=Payment.Status.PENDING,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        future = Payment.objects.create(
            address=address,
            amount=5000,
            payer_email="vecino@example.cl",
            gateway="flow",
            status=Payment.Status.PENDING,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        paid = Payment.objects.create(
            address=address,
            amount=5000,
            payer_email="vecino@example.cl",
            gateway="flow",
            status=Payment.Status.PAID,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        ids = expire_pending_flow_payments()
        self.assertIn(expired.pk, ids)
        expired.refresh_from_db()
        future.refresh_from_db()
        paid.refresh_from_db()
        self.assertEqual(expired.status, Payment.Status.EXPIRED)
        self.assertEqual(future.status, Payment.Status.PENDING)
        self.assertEqual(paid.status, Payment.Status.PAID)


@skipUnlessDBFeature("has_select_for_update")
@override_settings(SECURE_SSL_REDIRECT=False)
class FlowConcurrentWebhookTests(TransactionTestCase):
    @override_settings(FLOW_API_KEY="api-test", FLOW_SECRET_KEY="test-secret")
    def test_concurrent_webhooks_apply_payment_once(self):
        address = Address.objects.create(label="Pasaje Concurrente 88")
        charge = Charge.objects.create(
            address=address,
            period_year=2026,
            period_month=11,
            amount=9000,
            due_date=timezone.localdate(),
        )
        payment = Payment.objects.create(
            address=address,
            amount=9000,
            payer_email="vecino@example.cl",
            gateway="flow",
            gateway_preference_id="concurrent-token",
            metadata={"charge_ids": [charge.pk]},
        )
        payload = {"token": "concurrent-token"}
        payload["s"] = signed(payload)
        barrier = Barrier(2)
        responses = []

        def get_status(_token):
            barrier.wait(timeout=5)
            return {"status": 2}

        def send_webhook():
            close_old_connections()
            try:
                responses.append(Client().post(reverse("payments:flow_webhook"), payload).status_code)
            finally:
                close_old_connections()

        with patch("payments.views.FlowClient.get_status", side_effect=get_status):
            threads = [Thread(target=send_webhook), Thread(target=send_webhook)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=15)

        self.assertEqual(responses, [200, 200])
        self.assertEqual(PaymentAllocation.objects.filter(payment=payment, charge=charge).count(), 1)
        charge.refresh_from_db()
        self.assertEqual(charge.paid_amount, 9000)


@override_settings(SECURE_SSL_REDIRECT=False)
class CheckoutViewTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user(username="vecino", password="secret", email="vecino@example.cl")
        self.address = Address.objects.create(label="Los Aromos 010 Villa Concepción", user=self.user, owner_email=self.user.email)
        self.charge = Charge.objects.create(
            address=self.address,
            period_year=2026,
            period_month=11,
            amount=10000,
            due_date=timezone.localdate(),
        )

    def test_checkout_requires_login(self):
        response = self.client.get(reverse("payments:checkout"))
        self.assertEqual(response.status_code, 200)

    def test_checkout_is_public(self):
        response = self.client.get(reverse("payments:checkout"))
        self.assertEqual(response.status_code, 200)

    def test_checkout_public_entry_point(self):
        response = self.client.get(reverse("payments:checkout"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Revisa las cuotas de tu hogar")

        lookup = self.client.post(reverse("payments:checkout"), {"address": "los-aromos-10-villa concepcion"})
        self.assertRedirects(lookup, reverse("payments:checkout"))
        detail = self.client.get(reverse("payments:checkout"))
        self.assertContains(detail, "Los Aromos 010 Villa Concepción")
        self.assertContains(detail, str(self.charge.remaining_amount))
        self.assertNotContains(detail, self.address.owner_email)

    def test_checkout_lists_only_authenticated_users_charges(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("payments:checkout"))
        self.assertContains(response, "Los Aromos 010 Villa Concepción")
        self.assertContains(response, str(self.charge.remaining_amount))

    def test_paid_payment_cannot_be_deleted_but_pending_uses_soft_delete(self):
        from django.db.models import ProtectedError

        address = Address.objects.create(label="Pasaje Seguro 22")
        paid = Payment.objects.create(
            address=address,
            amount=1000,
            payer_email="vecino@example.cl",
            status=Payment.Status.PAID,
        )
        pending = Payment.objects.create(
            address=address,
            amount=1000,
            payer_email="vecino@example.cl",
            status=Payment.Status.PENDING,
        )
        with self.assertRaises(ProtectedError):
            paid.delete()
        pending.delete()
        pending.refresh_from_db()
        self.assertIsNotNone(pending.deleted_at)
        self.assertFalse(Payment.objects.filter(pk=pending.pk).exists())
        self.assertTrue(Payment.all_objects.filter(pk=pending.pk).exists())

    def test_address_suggestions_match_partial_text_without_exposing_owner_data(self):
        response = self.client.get(reverse("payments:address_suggestions"), {"q": "aromos 10"})

        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual(results, [{"id": self.address.pk, "label": "Los Aromos 010 Villa Concepción"}])
        self.assertNotIn("owner_email", response.content.decode())
        self.assertNotIn(self.address.owner_email, response.content.decode())

    def test_checkout_accepts_an_explicit_suggestion(self):
        response = self.client.post(reverse("payments:checkout"), {
            "address": self.address.label,
            "address_id": self.address.pk,
        })

        self.assertRedirects(response, reverse("payments:checkout"))
        detail = self.client.get(reverse("payments:checkout"))
        self.assertContains(detail, self.address.label)

    def test_checkout_does_not_guess_ambiguous_partial_address(self):
        response = self.client.post(reverse("payments:checkout"), {"address": "Los Aromos 10"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Selecciona tu dirección de la lista de sugerencias")
