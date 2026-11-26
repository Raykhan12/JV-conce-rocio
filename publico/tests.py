from django.test import TestCase
from django.urls import reverse

from .models import Noticia


class PublicDesignSmokeTests(TestCase):
    def setUp(self):
        self.noticia = Noticia.objects.create(
            titulo="Noticia de prueba",
            contenido="Contenido de verificación para la portada y la vista de detalle.",
            publicada=True,
        )

    def test_public_pages_render(self):
        paths = [
            reverse("inicio"),
            reverse("noticias"),
            reverse("formularios"),
            reverse("estatutos"),
            reverse("certificado"),
            reverse("denuncia"),
            reverse("ingreso"),
            reverse("panel_login"),
            reverse("noticia_detalle", args=[self.noticia.pk]),
        ]

        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)

    def test_public_layout_loads_local_design_assets(self):
        response = self.client.get(reverse("inicio"))

        self.assertContains(response, "css/tailwind.css")
        self.assertContains(response, "css/site.css")
        self.assertContains(response, "css/community.css")
        self.assertContains(response, "js/site.js")
        self.assertContains(response, "Contactar a Tesorería")
        self.assertContains(response, "whatsapp-float")
        self.assertNotContains(response, "cdn.tailwindcss.com")
