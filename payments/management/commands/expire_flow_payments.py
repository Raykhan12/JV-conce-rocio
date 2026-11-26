from django.core.management.base import BaseCommand

from payments.expiration import expire_pending_flow_payments


class Command(BaseCommand):
    help = "Marca como expirados los pagos Flow pendientes cuya fecha venció."

    def handle(self, *args, **options):
        expired_ids = expire_pending_flow_payments()
        self.stdout.write(self.style.SUCCESS(f"Pagos expirados: {len(expired_ids)}"))
