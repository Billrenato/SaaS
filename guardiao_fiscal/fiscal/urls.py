from django.urls import path
from .views import upload_xml
from .views import listar_notas

urlpatterns = [
    path("upload/", upload_xml, name="upload"),
    path("notas/", listar_notas, name="listar_notas"),
]