from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from payments.models import Address, Charge, Expense, Payment, PaymentAllocation, PaymentEvent
import shutil
import tempfile


@override_settings(SECURE_SSL_REDIRECT=False)
class AccountingPanelTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()

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
        Payment.objects.create(
            address=address,
            amount=2500,
            payer_email="pagador@example.cl",
            status=Payment.Status.PAID,
            paid_at=timezone.now(),
            gateway="manual",
            payment_method="cash",
            source="historical_word",
        )

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

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
        self.assertContains(staff, "7.500")
        self.assertContains(staff, "Último mes pagado")
        self.assertContains(staff, "Monto adeudado")
        self.assertContains(staff, "Solo con deuda")
        self.assertContains(staff, "Monto mínimo de pago")
        self.assertContains(staff, "Ordenar por dirección")
        self.assertContains(staff, "Ordenar por fecha")
        self.assertContains(staff, "Ordenar por monto")
        self.assertNotContains(staff, "id=\"payment-income-sort\"")

    def test_accounting_csv_exports_all_payment_sources(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("contabilidad_export"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        body = response.content.decode("utf-8")
        self.assertIn("Cuota", body)
        self.assertIn("Pasaje Contable 55", body)
        self.assertIn("Pago cuotas", body)
        self.assertIn("Flow", body)
        self.assertIn("Efectivo", body)
        self.assertIn("Pasaje Contable 55", body)

    def test_staff_can_register_manual_payment_with_method(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("registrar_pago_cuota"), {
            "address_id": self.charge.address_id,
            "amount": 3000,
            "payment_date": timezone.localdate().isoformat(),
            "payment_method": "bank_transfer",
            "payer_name": "Vecino Prueba",
            "reference": "DEP-123",
            "note": "Pago en banco",
        })

        self.assertRedirects(response, reverse("contabilidad"))
        self.charge.refresh_from_db()
        self.assertEqual(self.charge.status, Charge.Status.PARTIAL)
        self.assertEqual(self.charge.paid_amount, 5500)
        payment = Payment.objects.get(source="manual_panel")
        self.assertEqual(payment.amount, 3000)
        self.assertEqual(payment.payment_method, "bank_transfer")
        self.assertEqual(payment.gateway_payment_id, "DEP-123")
        self.assertEqual(payment.metadata["payment_method_label"], "Transferencia bancaria")
        self.assertEqual(PaymentAllocation.objects.get(payment=payment).amount, 3000)
        self.assertTrue(PaymentEvent.objects.filter(payment=payment, event_type="manual.panel_payment").exists())

    def test_manual_payment_cannot_exceed_pending_debt(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("registrar_pago_cuota"), {
            "address_id": self.charge.address_id,
            "amount": 999999,
            "payment_date": timezone.localdate().isoformat(),
            "payment_method": "cash",
        })

        self.assertRedirects(response, reverse("contabilidad"))
        self.assertFalse(Payment.objects.filter(source="manual_panel").exists())
        self.charge.refresh_from_db()
        self.assertEqual(self.charge.paid_amount, 2500)

    def test_staff_can_register_expense_with_private_receipt(self):
        self.client.force_login(self.staff)
        receipt = SimpleUploadedFile("boleta.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        response = self.client.post(reverse("registrar_gasto"), {
            "description": "Compra de materiales",
            "amount": 12500,
            "expense_date": timezone.localdate().isoformat(),
            "category": Expense.Category.SUPPLIES,
            "payment_method": Expense.PaymentMethod.BANK_TRANSFER,
            "vendor": "Proveedor Prueba",
            "reference": "FAC-88",
            "notes": "Aprobado",
            "receipt": receipt,
        })

        self.assertRedirects(response, reverse("contabilidad"))
        expense = Expense.objects.get(reference="FAC-88")
        self.assertEqual(expense.amount, 12500)
        self.assertEqual(expense.registered_by, self.staff)
        self.assertTrue(expense.receipt.name.startswith("private/expenses/"))

        direct = self.client.get(f"/media/{expense.receipt.name}")
        self.assertEqual(direct.status_code, 404)

        download = self.client.get(reverse("expense_receipt", args=[expense.pk]))
        self.assertEqual(download.status_code, 200)
        self.client.logout()
        anonymous = self.client.get(reverse("expense_receipt", args=[expense.pk]))
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn(reverse("panel_login"), anonymous.url)

        dashboard = self.client.force_login(self.staff) or self.client.get(reverse("contabilidad"))
        self.assertContains(dashboard, "12.500")

    def test_regular_user_cannot_register_expense(self):
        self.client.force_login(self.regular)
        response = self.client.post(reverse("registrar_gasto"), {
            "description": "No autorizado",
            "amount": 1000,
            "expense_date": timezone.localdate().isoformat(),
            "category": Expense.Category.OTHER,
            "payment_method": Expense.PaymentMethod.CASH,
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Expense.objects.exists())

    def test_expense_cannot_have_nonpositive_amount_or_oversized_receipt(self):
        self.client.force_login(self.staff)
        invalid = self.client.post(reverse("registrar_gasto"), {
            "description": "Monto inválido",
            "amount": 0,
            "expense_date": timezone.localdate().isoformat(),
            "category": Expense.Category.OTHER,
            "payment_method": Expense.PaymentMethod.CASH,
        })
        self.assertRedirects(invalid, reverse("contabilidad"))
        self.assertFalse(Expense.objects.exists())

        oversized = SimpleUploadedFile("boleta.pdf", b"x" * (10 * 1024 * 1024 + 1), content_type="application/pdf")
        too_large = self.client.post(reverse("registrar_gasto"), {
            "description": "Archivo grande",
            "amount": 1000,
            "expense_date": timezone.localdate().isoformat(),
            "category": Expense.Category.OTHER,
            "payment_method": Expense.PaymentMethod.CASH,
            "receipt": oversized,
        })
        self.assertRedirects(too_large, reverse("contabilidad"))
        self.assertFalse(Expense.objects.exists())
