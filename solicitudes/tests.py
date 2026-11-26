from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from payments.models import Address, Charge, Payment


@override_settings(SECURE_SSL_REDIRECT=False)
class AccountingPanelTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(username="admin", password="secret", is_staff=True)
        self.regular = user_model.objects.create_user(username="vecino", password="secret")
        address = Address.objects.create(label="Pasaje Contable 55", owner_name="Titular")
        self.charge = Charge.objects.create(
            address=address,
            period_year=2026,
            period_month=11,
            amount=10000,
            paid_amount=2500,
            status=Charge.Status.PARTIAL,
            due_date=timezone.localdate(),
        )
        Payment.objects.create(
            address=address,
            amount=2500,
            payer_email="pagador@example.cl",
            status=Payment.Status.PAID,
            paid_at=timezone.now(),
        )

    def test_accounting_requires_staff_panel_user(self):
        anonymous = self.client.get(reverse("contabilidad"))
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn(reverse("panel_login"), anonymous.url)

        self.client.force_login(self.regular)
        regular = self.client.get(reverse("contabilidad"))
        self.assertEqual(regular.status_code, 302)

        self.client.force_login(self.staff)
        staff = self.client.get(reverse("contabilidad"))
        self.assertEqual(staff.status_code, 200)
        self.assertContains(staff, "Pasaje Contable 55")
        self.assertContains(staff, "7500")

    def test_accounting_csv_exports_all_payment_sources(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("contabilidad_export"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        body = response.content.decode("utf-8")
        self.assertIn("Cuota", body)
        self.assertIn("Pago Flow", body)
        self.assertIn("Pasaje Contable 55", body)
