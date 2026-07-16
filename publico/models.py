from django.db import models


class Noticia(models.Model):
    titulo    = models.CharField('Título', max_length=200)
    contenido = models.TextField('Contenido')
    imagen    = models.ImageField('Imagen', upload_to='noticias/', blank=True)
    publicada = models.BooleanField('Publicada', default=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Noticia'
        verbose_name_plural = 'Noticias'
        ordering            = ['-creado_en']

    def __str__(self):
        return self.titulo
