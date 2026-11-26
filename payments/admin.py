from django.contrib import admin

from payments.models import Address, Charge, Expense, FeeConfig, Payment, PaymentAllocation, PaymentEvent


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("label", "owner_name", "owner_email", "active")
    search_fields = ("label", "owner_name", "owner_email")


@admin.register(FeeConfig)
class FeeConfigAdmin(admin.ModelAdmin):
    list_display = ("amount", "valid_from", "valid_to")
    ordering = ("-valid_from",)


@admin.register(Charge)
class ChargeAdmin(admin.ModelAdmin):
    list_display = ("address", "period_year", "period_month", "amount", "paid_amount", "status", "due_date")
    list_filter = ("status", "period_year", "period_month")
    search_fields = ("address__label",)


class AllocationInline(admin.TabularInline):
    model = PaymentAllocation
    extra = 0
    readonly_fields = ("payment", "charge", "amount", "created_at")
    can_delete = False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "address", "amount", "status", "gateway", "payer_email", "created_at", "paid_at")
    list_filter = ("status", "source", "gateway")
    search_fields = ("payer_email", "payer_name", "payer_rut", "gateway_payment_id", "gateway_preference_id")
    readonly_fields = ("created_at", "updated_at", "deleted_at")
    inlines = (AllocationInline,)


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = ("gateway", "event_type", "external_id", "payment", "processed", "created_at")
    list_filter = ("processed", "gateway", "event_type")
    search_fields = ("external_id", "payment__id")
    readonly_fields = ("created_at", "processed_at")


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("expense_date", "description", "category", "amount", "payment_method", "vendor", "registered_by")
    list_filter = ("category", "payment_method", "expense_date", "registered_by")
    search_fields = ("description", "vendor", "reference", "notes")
    readonly_fields = ("registered_by", "created_at", "updated_at", "deleted_at")

    def has_delete_permission(self, request, obj=None):
        return False
