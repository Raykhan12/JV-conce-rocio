from django.urls import path
from . import views

urlpatterns = [
    path('panel/ingresar/',               views.panel_login,         name='panel_login'),
    path('panel/',                        views.dashboard,           name='dashboard'),
    path('panel/salir/',                  views.panel_logout,        name='panel_logout'),
    path('panel/certificado/<int:pk>/',   views.detalle_certificado, name='detalle_certificado'),
    path('panel/denuncia/<int:pk>/',      views.detalle_denuncia,    name='detalle_denuncia'),
]
