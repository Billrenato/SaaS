import requests
from django.core.management.base import BaseCommand
from fiscal.models import Empresa
from fiscal.services import ler_xml

API_URL = "http://localhost:9000"


class Command(BaseCommand):

    def handle(self, *args, **kwargs):

        empresas = Empresa.objects.all()

        for empresa in empresas:

            r = requests.get(f"{API_URL}/documentos/{empresa.cnpj}")

            if r.status_code != 200:
                print("Erro API:", r.text)
                continue

            documentos = r.json()

            if not documentos:
                print("Nenhum XML para", empresa.cnpj)
                continue

            for doc in documentos:

                url_download = API_URL + doc["download"]

                xml_bytes = requests.get(url_download).content

                status = ler_xml(xml_bytes, empresa)

                print(doc["arquivo"], status)