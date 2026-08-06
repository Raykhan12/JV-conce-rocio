from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('solicitudes', '0003_add_numeros'),
    ]

    operations = [
        migrations.AddField(
            model_name='solicitudcertificado',
            name='valor_cobrado',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Valor cobrado ($)'),
        ),
        migrations.AddField(
            model_name='solicitudcertificado',
            name='num_recibo',
            field=models.CharField(blank=True, max_length=20, verbose_name='N° de recibo'),
        ),
        migrations.AddField(
            model_name='solicitudcertificado',
            name='fecha_pago',
            field=models.DateField(blank=True, null=True, verbose_name='Fecha de pago'),
        ),
        migrations.AddField(
            model_name='solicitudcertificado',
            name='fecha_entrega',
            field=models.DateField(blank=True, null=True, verbose_name='Fecha de entrega'),
        ),
    ]
