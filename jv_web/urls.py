from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve
from django.http import HttpResponseNotFound

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('publico.urls')),
    path('', include('solicitudes.urls')),
    path('', include('payments.urls')),
    re_path(r'^media/private/.*$', lambda request: HttpResponseNotFound()),
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
