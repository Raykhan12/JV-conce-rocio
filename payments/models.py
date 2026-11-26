from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import ProtectedError, Q
from django.utils import timezone
from datetime import date


class ActivePaymentQuerySet(models.QuerySet):
    def delete(self):
        paid = self.filter(status=Payment.Status.PAID).exists()
        if paid:
            raise ProtectedError("Los pagos confirmados no pueden eliminarse.", list(self.filter(status=Payment.Status.PAID)))
        return super().update(deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()


class ActivePaymentManager(models.Manager):
    def get_queryset(self):
        return ActivePaymentQuerySet(self.model, using=self._db).filter(deleted_at__isnull=True)


class Address(models.Model):
    label = models.CharField("Dirección", max_length=200, unique=True)
    owner_name = models.CharField("Nombre del titular", max_length=150, blank=True)
    owner_email = models.EmailField("Correo del titular", blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="addresses",
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "addresses"
        ordering = ["label"]

    def __str__(self):
        return self.label


class FeeConfig(models.Model):
    community_id = models.PositiveBigIntegerField(null=True, blank=True)
    name = models.CharField(max_length=100, default="Cuota mensual")
    amount = models.PositiveIntegerField(help_text="Monto en CLP")
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    due_day = models.PositiveSmallIntegerField(default=10)
    late_fee_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "fee_configs"
        ordering = ["-valid_from"]
        indexes = [models.Index(fields=["valid_from", "valid_to"])]
        constraints = [
            models.CheckConstraint(condition=Q(due_day__gte=1, due_day__lte=31), name="ck_fee_due_day"),
            models.CheckConstraint(
                condition=Q(late_fee_percent__isnull=True) | Q(late_fee_percent__lte=100),
                name="ck_fee_late_percent",
            ),
        ]

    def clean(self):
        super().clean()
        if self.valid_to and self.valid_to < self.valid_from:
            raise ValidationError({"valid_to": "La fecha final no puede ser anterior a la inicial."})
        overlap = FeeConfig.objects.filter(valid_from__lte=self.valid_to or date.max).filter(
            Q(valid_to__isnull=True) | Q(valid_to__gte=self.valid_from)
        )
        if self.pk:
            overlap = overlap.exclude(pk=self.pk)
        if overlap.exists():
            raise ValidationError("El rango de vigencia se superpone con otra configuración.")

    def __str__(self):
        return f"Cuota ${self.amount} desde {self.valid_from}"


class Charge(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        PARTIAL = "partial", "Parcial"
        PAID = "paid", "Pagado"
        OVERDUE = "overdue", "Vencido"
        WAIVED = "waived", "Condonado"
        CANCELLED = "cancelled", "Cancelado"

    address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name="charges")
    period_year = models.PositiveSmallIntegerField()
    period_month = models.PositiveSmallIntegerField()
    amount = models.PositiveIntegerField(help_text="Monto original en CLP")
    due_date = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    paid_amount = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ActivePaymentManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "charges"
        constraints = [
            models.UniqueConstraint(
                fields=["address", "period_year", "period_month"],
                name="uq_charge_address_period",
            ),
            models.CheckConstraint(condition=Q(paid_amount__gte=0), name="ck_charge_paid_nonnegative"),
            models.CheckConstraint(condition=Q(paid_amount__lte=models.F("amount")), name="ck_charge_paid_not_exceed"),
            models.CheckConstraint(condition=Q(period_month__gte=1, period_month__lte=12), name="ck_charge_month"),
        ]
        indexes = [
            models.Index(fields=["address", "status", "due_date"]),
            models.Index(fields=["address", "period_year", "period_month"]),
        ]
        ordering = ["due_date", "pk"]

    @property
    def remaining_amount(self):
        return max(0, self.amount - self.paid_amount)

    def refresh_payment_status(self, save=True):
        if self.paid_amount >= self.amount:
            self.status = self.Status.PAID
        elif self.paid_amount > 0:
            self.status = self.Status.PARTIAL
        elif self.due_date < timezone.localdate():
            self.status = self.Status.OVERDUE
        else:
            self.status = self.Status.PENDING
        if save:
            self.save(update_fields=["paid_amount", "status", "updated_at"])

    def delete(self, using=None, keep_parents=False):
        if self.status == self.Status.PAID:
            raise ProtectedError("Los cargos pagados no pueden eliminarse.", [self])
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"], using=using)

    def soft_delete(self, using=None):
        self.delete(using=using)

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)

    def __str__(self):
        return f"{self.address} · {self.period_year}-{self.period_month:02d}"


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        PROCESSING = "processing", "Procesando"
        PAID = "paid", "Pagado"
        FAILED = "failed", "Fallido"
        CANCELLED = "cancelled", "Cancelado"
        EXPIRED = "expired", "Expirado"

    address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name="payments")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    amount = models.PositiveIntegerField(help_text="Monto total en CLP")
    currency = models.CharField(max_length=3, default="CLP")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    source = models.CharField(max_length=32, default="online")
    payment_method = models.CharField(max_length=32, default="flow", null=True, blank=True)
    gateway = models.CharField(max_length=32, default="flow")
    gateway_payment_id = models.CharField(max_length=120, null=True, blank=True, db_index=True)
    gateway_preference_id = models.CharField(max_length=120, null=True, blank=True, db_index=True)
    payer_email = models.EmailField()
    payer_name = models.CharField(max_length=150, blank=True)
    payer_rut = models.CharField(max_length=20, blank=True)
    description = models.TextField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ActivePaymentManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "payments"
        indexes = [
            models.Index(fields=["address", "status"]),
            models.Index(fields=["status", "expires_at"]),
        ]
        ordering = ["-created_at"]

    def delete(self, using=None, keep_parents=False):
        if self.status == self.Status.PAID:
            raise ProtectedError("Los pagos confirmados no pueden eliminarse.", [self])
        self.soft_delete(using=using)

    def soft_delete(self, using=None):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"], using=using)

    @property
    def allocated_amount(self):
        return sum(allocation.amount for allocation in self.allocations.all())

    @property
    def amount_remaining(self):
        return max(0, self.amount - self.allocated_amount)

    def apply_to_charges(self, charge_ids=None):
        from payments.services.apply_payment import apply_payment_to_charges

        return apply_payment_to_charges(self, charge_ids)

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)

    def __str__(self):
        return f"Pago #{self.pk} · ${self.amount} · {self.status}"


class PaymentAllocation(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="allocations")
    charge = models.ForeignKey(Charge, on_delete=models.PROTECT, related_name="allocations")
    amount = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payment_allocations"
        constraints = [
            models.UniqueConstraint(fields=["payment", "charge"], name="uq_allocation_payment_charge"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="ck_allocation_amount_positive"),
        ]
        indexes = [models.Index(fields=["charge"])]


class PaymentEvent(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name="events")
    gateway = models.CharField(max_length=32, default="flow")
    event_type = models.CharField(max_length=64)
    external_id = models.CharField(max_length=160, unique=True)
    payload = models.JSONField(default=dict, blank=True)
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payment_events"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["gateway", "event_type", "created_at"])]

    def __str__(self):
        return f"{self.gateway}:{self.event_type}:{self.external_id}"
