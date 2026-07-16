from django.contrib import admin
from .models import Noticia


@admin.register(Noticia)
class NoticiaAdmin(admin.ModelAdmin):
    list_display  = ('titulo', 'publicada', 'creado_en')
    list_filter   = ('publicada',)
    list_editable = ('publicada',)
    search_fields = ('titulo', 'contenido')
    readonly_fields = ('creado_en',)
