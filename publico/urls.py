from django.urls import path
from . import views

urlpatterns = [
    path('',                           views.inicio,        name='inicio'),
    path('noticias/',                  views.noticias,      name='noticias'),
    path('formularios/',               views.formularios,   name='formularios'),
    path('formularios/certificado/',   views.certificado,   name='certificado'),
    path('formularios/certificado/exito/', views.cert_exito, name='cert_exito'),
    path('formularios/denuncia/',      views.denuncia,      name='denuncia'),
    path('formularios/denuncia/exito/', views.denuncia_exito, name='denuncia_exito'),
]
