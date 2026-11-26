from django.urls import path

from payments import views

app_name = "payments"

urlpatterns = [
    path("payments/checkout/", views.checkout, name="checkout"),
    path("payments/flow/create/", views.create_flow_payment, name="flow_create"),
    path("webhooks/flow/", views.flow_webhook, name="flow_webhook"),
    path("payments/flow/return/", views.flow_return, name="flow_return"),
]
