from django.db import migrations, models


def populate_numeros(apps, schema_editor):
    SolicitudCertificado = apps.get_model('solicitudes', 'SolicitudCertificado')
    SolicitudIngreso     = apps.get_model('solicitudes', 'SolicitudIngreso')
    DenunciaVecinal      = apps.get_model('solicitudes', 'DenunciaVecinal')

    for Model, prefix in [
        (SolicitudCertificado, 'CR'),
        (SolicitudIngreso,     'SI'),
        (DenunciaVecinal,      'DV'),
    ]:
        for obj in Model.objects.filter(numero='').order_by('creado_en'):
            year = obj.creado_en.year
            prefix_year = f'{prefix}-{year}-'
            existing = [
                int(n.split('-')[-1])
                for n in Model.objects.filter(numero__startswith=prefix_year)
                                      .values_list('numero', flat=True)
                if n and n.split('-')[-1].isdigit()
            ]
            obj.numero = f'{prefix_year}{str(max(existing, default=0) + 1).zfill(3)}'
            obj.save()


class Migration(migrations.Migration):

    dependencies = [
        ('solicitudes', '0002_solicitudingreso'),
    ]

    operations = [
        # 1. Agregar campos (sin unique todavía)
        migrations.AddField(
            model_name='solicitudcertificado',
            name='numero',
            field=models.CharField(blank=True, default='', max_length=20, verbose_name='N° Solicitud'),
        ),
        migrations.AddField(
            model_name='solicitudingreso',
            name='numero',
            field=models.CharField(blank=True, default='', max_length=20, verbose_name='N° Solicitud'),
        ),
        migrations.AddField(
            model_name='denunciavecinal',
            name='numero',
            field=models.CharField(blank=True, default='', max_length=20, verbose_name='N° Denuncia'),
        ),
        # 2. Poblar registros existentes
        migrations.RunPython(populate_numeros, migrations.RunPython.noop),
        # 3. Agregar restricción unique
        migrations.AlterField(
            model_name='solicitudcertificado',
            name='numero',
            field=models.CharField(max_length=20, unique=True, verbose_name='N° Solicitud'),
        ),
        migrations.AlterField(
            model_name='solicitudingreso',
            name='numero',
            field=models.CharField(max_length=20, unique=True, verbose_name='N° Solicitud'),
        ),
        migrations.AlterField(
            model_name='denunciavecinal',
            name='numero',
            field=models.CharField(max_length=20, unique=True, verbose_name='N° Denuncia'),
        ),
    ]
