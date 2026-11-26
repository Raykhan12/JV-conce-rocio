from django.urls import path
from . import views

urlpatterns = [
    path('panel/ingresar/',               views.panel_login,         name='panel_login'),
    path('panel/',                        views.dashboard,           name='dashboard'),
    path('panel/contabilidad/',           views.contabilidad,        name='contabilidad'),
    path('panel/contabilidad/registrar-pago/', views.registrar_pago_cuota, name='registrar_pago_cuota'),
    path('panel/contabilidad/registrar-gasto/', views.registrar_gasto, name='registrar_gasto'),
    path('panel/contabilidad/gastos/<int:pk>/comprobante/', views.expense_receipt, name='expense_receipt'),
    path('panel/contabilidad/exportar/',  views.contabilidad_export, name='contabilidad_export'),
    path('panel/salir/',                  views.panel_logout,        name='panel_logout'),
    path('panel/certificado/<int:pk>/',   views.detalle_certificado, name='detalle_certificado'),
    path('panel/denuncia/<int:pk>/',      views.detalle_denuncia,    name='detalle_denuncia'),
    path('panel/ingreso/<int:pk>/',       views.detalle_ingreso,     name='detalle_ingreso'),
]
