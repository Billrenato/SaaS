import zipfile
import rarfile
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal
from .models import NotaFiscal


def processar_lote(upload_lote):
    caminho = upload_lote.arquivo.path
    pasta_temp = os.path.dirname(caminho)

    arquivos_xml = []

    # CASO 1: XML DIRETO
    if caminho.lower().endswith(".xml"):
        arquivos_xml.append(caminho)

    # CASO 2: ZIP
    elif caminho.lower().endswith(".zip"):
        with zipfile.ZipFile(caminho, 'r') as zip_ref:
            zip_ref.extractall(pasta_temp)

    # CASO 3: RAR
    elif caminho.lower().endswith(".rar"):
        with rarfile.RarFile(caminho) as rar_ref:
            rar_ref.extractall(pasta_temp)

    # 🔎 PROCURA XML RECURSIVAMENTE
    for raiz, pastas, arquivos in os.walk(pasta_temp):
        for arquivo in arquivos:
            if arquivo.lower().endswith(".xml"):
                caminho_xml = os.path.join(raiz, arquivo)
                arquivos_xml.append(caminho_xml)

    print("XML encontrados:", arquivos_xml)

    for caminho_xml in arquivos_xml:
        ler_xml(caminho_xml, upload_lote.empresa)

def ler_xml(caminho_xml, empresa):
    tree = ET.parse(caminho_xml)
    root = tree.getroot()

    def buscar(tag):
        return root.find(f".//{{*}}{tag}")

    chave_tag = buscar("infNFe")
    numero = buscar("nNF")
    data = buscar("dhEmi")
    valor = buscar("vNF")

    cnpj_emit = buscar("CNPJ")
    cnpj_dest = root.find(".//{*}dest/{*}CNPJ")

    icms = buscar("vICMS")
    ipi = buscar("vIPI")
    pis = buscar("vPIS")
    cofins = buscar("vCOFINS")
    tributos = buscar("vTotTrib")

    if not (chave_tag is not None and numero is not None and data is not None and valor is not None):
        print("Campos obrigatórios ausentes:", caminho_xml)
        return

    chave = chave_tag.attrib.get("Id", "").replace("NFe", "")

    # -------- TIPO --------
    modelo = buscar("mod")
    if modelo is not None and modelo.text == "65":
        tipo = "nfce"
    else:
        if cnpj_emit is not None and cnpj_emit.text == empresa.cnpj:
            tipo = "saida"
        else:
            tipo = "entrada"

    if NotaFiscal.objects.filter(chave=chave).exists():
        return

    NotaFiscal.objects.create(
        empresa=empresa,
        chave=chave,
        numero=numero.text,
        data_emissao=datetime.fromisoformat(data.text.replace("Z", "")),
        valor_total=Decimal(valor.text),

        valor_icms=Decimal(icms.text) if icms is not None else 0,
        valor_ipi=Decimal(ipi.text) if ipi is not None else 0,
        valor_pis=Decimal(pis.text) if pis is not None else 0,
        valor_cofins=Decimal(cofins.text) if cofins is not None else 0,
        valor_tributos=Decimal(tributos.text) if tributos is not None else 0,

        tipo=tipo
    )

    print("Nota salva:", chave)
