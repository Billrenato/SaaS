import zipfile
import rarfile
import py7zr  # Importação necessária para o seu arquivo .7z
import xml.etree.ElementTree as ET
import logging
import os
import shutil
import tempfile
import re
from datetime import datetime
from decimal import Decimal
from django.db import transaction
from .models import NotaFiscal

logger = logging.getLogger(__name__)

def apenas_numeros(valor):
    
    return re.sub(r'\D', '', str(valor))

def processar_lote(upload_lote):
    caminho = upload_lote.arquivo.path
    empresa = upload_lote.empresa
    
    # Criamos uma pasta temporária para garantir a leitura de subpastas e formatos complexos
    pasta_temp = tempfile.mkdtemp()

    try:
        # 1. Extração baseada na extensão
        if caminho.lower().endswith(".7z"):
            with py7zr.SevenZipFile(caminho, mode='r') as archive:
                archive.extractall(path=pasta_temp)
        
        elif caminho.lower().endswith(".zip"):
            with zipfile.ZipFile(caminho, 'r') as zip_ref:
                zip_ref.extractall(path=pasta_temp)

        elif caminho.lower().endswith(".rar"):
            with rarfile.RarFile(caminho) as rar_ref:
                rar_ref.extractall(path=pasta_temp)

        # 2. Varredura recursiva (entra em todas as subpastas)
        for raiz, _, arquivos in os.walk(pasta_temp):
            for nome in arquivos:
                if nome.lower().endswith(".xml"):
                    caminho_xml = os.path.join(raiz, nome)
                    with open(caminho_xml, 'rb') as f:
                        ler_xml(f.read(), empresa)

    except Exception as e:
        logger.error(f"Erro ao processar lote {upload_lote.id}: {e}")
    finally:
        # 3. Limpeza obrigatória da pasta temporária
        shutil.rmtree(pasta_temp)

@transaction.atomic
def ler_xml(xml_bytes, empresa):
    try:
        root = ET.fromstring(xml_bytes)
    except Exception as e:
        logger.error(f"Erro ao parsear XML: {e}")
        return

    ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}

    # Localiza a tag principal infNFe (funciona para nfeProc ou NFe)
    infNFe = root.find(".//ns:infNFe", ns)
    if infNFe is None:
        return

    ide = root.find(".//ns:ide", ns)
    if ide is None:
        return

    # Dados básicos
    numero = ide.find("ns:nNF", ns).text
    modelo = ide.find("ns:mod", ns).text
    data_str = ide.find("ns:dhEmi", ns).text
    chave = infNFe.attrib.get("Id", "").replace("NFe", "")

    # Evita duplicidade
    if NotaFiscal.objects.filter(chave=chave).exists():
        return

    # --- LÓGICA DE TIPO (Entrada, Saída, NFC-e) ---
    emit = root.find(".//ns:emit", ns)
    cnpj_emitente = apenas_numeros(emit.find("ns:CNPJ", ns).text) if emit is not None else ""
    cnpj_minha_empresa = apenas_numeros(empresa.cnpj)

    if modelo == "65":
        tipo_nota = "nfce"
    else:
        # Se o CNPJ do emitente no XML for o meu, eu vendi (Saída). 
        # Se for diferente, eu comprei (Entrada).
        tipo_nota = "saida" if cnpj_emitente == cnpj_minha_empresa else "entrada"

    # --- FINANCEIRO ---
    icms_tot = root.find(".//ns:ICMSTot", ns)
    
    def get_decimal(tag):
        if icms_tot is None: return Decimal("0.00")
        el = icms_tot.find(f"ns:{tag}", ns)
        try:
            return Decimal(el.text) if el is not None else Decimal("0.00")
        except:
            return Decimal("0.00")

    # --- SALVAMENTO ---
    try:
        data_emissao = datetime.fromisoformat(data_str.replace("Z", ""))
        
        NotaFiscal.objects.create(
            empresa=empresa,
            chave=chave,
            numero=numero,
            data_emissao=data_emissao,
            valor_total=get_decimal("vNF"),
            valor_icms=get_decimal("vICMS"),
            valor_ipi=get_decimal("vIPI"),
            valor_pis=get_decimal("vPIS"),
            valor_cofins=get_decimal("vCOFINS"),
            valor_tributos=get_decimal("vTotTrib"),
            tipo=tipo_nota
        )
        print(f"[INFO] Nota {numero} ({tipo_nota.upper()}) salva com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao salvar nota {chave}: {e}")



