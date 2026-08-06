from django.db import migrations


NOTICIAS = [
    {
        'titulo': 'Firma de Convenio: $120.000.000 para Área Verde Los Naranjos 3',
        'contenido': (
            'Queridas vecinas y vecinos:\n\n'
            'Nos alegra compartir con ustedes que hoy estuvimos presentes en la ceremonia de firma del '
            'convenio entre el Alcalde y el Gobernador Regional, instancia en la que se oficializó el '
            'traspaso de $120.000.000 para la ejecución del proyecto "Área Verde: Los Naranjos 3"\n\n'
            'Gracias a nuestras vecinas Pabla Olivares, Belda Sepulveda y Dargy quienes representaron '
            'a nuestra comunidad en esta significativa ceremonia.'
        ),
        'imagenes': ['noticias/noticia1.jpg'],
    },
    {
        'titulo': 'Reunión con la Dirección de Seguridad Pública Municipal',
        'contenido': (
            'Estimados vecinos y vecinas:\n\n'
            'Queremos agradecer sinceramente a quienes participaron en la reunión realizada junto a la '
            'Dirección de Seguridad Pública de la Municipalidad de Concepción. Esta instancia nos '
            'permitió exponer las principales problemáticas que afectan a nuestras Villas Concepción y '
            'El Rocío, además de recibir orientación respecto de las herramientas y canales disponibles '
            'para abordarlas.\n\n'
            'Como resultado de esta reunión, se comprometió nuestra incorporación a la Mesa de '
            'Seguridad, a través de un grupo de WhatsApp que facilitará la comunicación directa con '
            'Seguridad Pública. Asimismo, se gestionará una reunión con la unidad de Carabineros '
            'responsable del Plan Cuadrante de nuestro sector y se acordó aumentar la frecuencia de '
            'las rondas preventivas de Seguridad Ciudadana en nuestras villas, con el propósito de '
            'fortalecer la coordinación y avanzar en soluciones para nuestra comunidad.\n\n'
            'Seguiremos trabajando de manera organizada y colaborativa, porque la seguridad es una '
            'tarea que requiere el compromiso de todos. Muchas gracias por su participación e interés.'
        ),
        'imagenes': ['noticias/noticia2_1.jpg', 'noticias/noticia2_2.jpg'],
    },
    {
        'titulo': '1.ª Asamblea Extraordinaria 2026 — ¡Gracias por participar!',
        'contenido': (
            'Queremos agradecer a todas las vecinas y vecinos que participaron en nuestra '
            '1.ª Asamblea Extraordinaria 2026. Su asistencia y compromiso son muy importantes '
            'para el trabajo de nuestra Junta de Vecinos. Los invitamos a seguir participando '
            'activamente en las próximas reuniones y actividades 😁'
        ),
        'imagenes': ['noticias/noticia3.jpg'],
    },
    {
        'titulo': 'Exitoso Operativo de Salud y Vacunación',
        'contenido': (
            'Estimados vecinos y vecinas:\n\n'
            'Queremos agradecer la gran participación en el operativo realizado hoy. Más de 40 '
            'personas asistieron a vacunarse y a realizarse exámenes médicos preventivos.\n\n'
            'También agradecemos a quienes manifestaron su interés en afiliarse a nuestra Junta de '
            'Vecinos y a nuestros socios que aprovecharon la instancia para ponerse al día con sus '
            'cuotas sociales.\n\n'
            'Este tipo de instancias nos motivan a seguir trabajando por nuestras villas y '
            'fortaleciendo la participación comunitaria.\n\n'
            '¡Muchas gracias a todos por su compromiso y confianza!\n\n'
            'Directiva Junta de Vecinos'
        ),
        'imagenes': ['noticias/noticia4.jpg'],
    },
]


def insertar_noticias(apps, schema_editor):
    Noticia = apps.get_model('publico', 'Noticia')
    NoticiaImagen = apps.get_model('publico', 'NoticiaImagen')
    for data in NOTICIAS:
        n = Noticia.objects.create(
            titulo=data['titulo'],
            contenido=data['contenido'],
            publicada=True,
        )
        for orden, path in enumerate(data['imagenes']):
            NoticiaImagen.objects.create(noticia=n, imagen=path, orden=orden)


def eliminar_noticias(apps, schema_editor):
    Noticia = apps.get_model('publico', 'Noticia')
    titulos = [d['titulo'] for d in NOTICIAS]
    Noticia.objects.filter(titulo__in=titulos).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('publico', '0002_noticiaimagen'),
    ]

    operations = [
        migrations.RunPython(insertar_noticias, eliminar_noticias),
    ]
