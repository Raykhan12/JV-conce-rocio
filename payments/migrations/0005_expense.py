from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("payments", "0004_charge_deleted_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="Expense",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("expense_date", models.DateField(verbose_name="Fecha del gasto")),
                ("category", models.CharField(choices=[("administration", "Administración"), ("services", "Servicios básicos"), ("maintenance", "Mantención y reparaciones"), ("community", "Actividades comunitarias"), ("support", "Ayuda social"), ("supplies", "Materiales e insumos"), ("infrastructure", "Obras e infraestructura"), ("other", "Otro")], max_length=32, verbose_name="Categoría")),
                ("description", models.CharField(max_length=240, verbose_name="Descripción")),
                ("amount", models.PositiveIntegerField(verbose_name="Monto en CLP")),
                ("vendor", models.CharField(blank=True, max_length=150, verbose_name="Proveedor o beneficiario")),
                ("payment_method", models.CharField(choices=[("cash", "Efectivo"), ("bank_transfer", "Transferencia bancaria"), ("deposit", "Depósito"), ("check", "Cheque"), ("other", "Otro")], max_length=32, verbose_name="Medio de pago")),
                ("reference", models.CharField(blank=True, max_length=120, verbose_name="N° de comprobante/documento")),
                ("notes", models.TextField(blank=True, verbose_name="Observaciones")),
                ("receipt", models.FileField(blank=True, upload_to="private/expenses/%Y/%m/", validators=[FileExtensionValidator(["pdf", "jpg", "jpeg", "png", "webp"])], verbose_name="Comprobante adjunto")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("registered_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="registered_expenses", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "expenses",
                "ordering": ["-expense_date", "-pk"],
                "indexes": [models.Index(fields=["expense_date", "category"], name="expenses_expense_6ed541_idx")],
                "constraints": [models.CheckConstraint(condition=models.Q(("amount__gt", 0)), name="ck_expense_amount_positive")],
            },
        ),
    ]
