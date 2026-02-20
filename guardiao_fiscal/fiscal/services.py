import zipfile
import rarfile
import py7zr
import xml.etree.ElementTree as ET
import logging
import os
import shutil
import tempfile
import re
from datetime import datetime
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Count # Adicionado para as métricas
from .models import NotaFiscal, NotaFiscalCFOP, UploadLote # Adicionado modelos extras

logger = logging.getLogger(__name__)

def apenas_numeros(valor):
    return re.sub(r'\D', '', str(valor))

def processar_lote(upload_lote):
    caminho = upload_lote.arquivo.path
    empresa = upload_lote.empresa
    pasta_temp = tempfile.mkdtemp()

    resultado = {
        "salvas": 0,
        "cnpj_invalido": 0,
        "duplicadas": 0,
        "xml_invalido": 0,
        "total": 0,
    }

    try:
        # EXTRAÇÃO (Mantido conforme seu original)
        if caminho.lower().endswith(".7z"):
            with py7zr.SevenZipFile(caminho, mode='r') as archive:
                archive.extractall(path=pasta_temp)
        elif caminho.lower().endswith(".zip"):
            with zipfile.ZipFile(caminho, 'r') as zip_ref:
                zip_ref.extractall(path=pasta_temp)
        elif caminho.lower().endswith(".rar"):
            with rarfile.RarFile(caminho) as rar_ref:
                rar_ref.extractall(path=pasta_temp)
        else:
            raise Exception("Formato de arquivo não suportado.")

        # VARREDURA
        for raiz, _, arquivos in os.walk(pasta_temp):
            for nome in arquivos:
                if nome.lower().endswith(".xml"):
                    resultado["total"] += 1
                    caminho_xml = os.path.join(raiz, nome)
                    try:
                        with open(caminho_xml, 'rb') as f:
                            status = ler_xml(f.read(), empresa)
                        if status == "salva":
                            resultado["salvas"] += 1
                        elif status == "cnpj_invalido":
                            resultado["cnpj_invalido"] += 1
                        elif status == "duplicada":
                            resultado["duplicadas"] += 1
                        elif status == "xml_invalido":
                            resultado["xml_invalido"] += 1
                    except Exception as e:
                        logger.error(f"Erro no XML {nome}: {e}")
                        resultado["xml_invalido"] += 1
        return resultado
    finally:
        shutil.rmtree(pasta_temp)

@transaction.atomic
def ler_xml(xml_bytes, empresa):
    try:
        root = ET.fromstring(xml_bytes)
    except:
        return "xml_invalido"

    ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
    infNFe = root.find(".//ns:infNFe", ns)
    ide = root.find(".//ns:ide", ns)

    if infNFe is None or ide is None:
        return "xml_invalido"

    numero = ide.find("ns:nNF", ns).text
    modelo = ide.find("ns:mod", ns).text
    data_str = ide.find("ns:dhEmi", ns).text
    chave = infNFe.attrib.get("Id", "").replace("NFe", "")

    if NotaFiscal.objects.filter(chave=chave).exists():
        return "duplicada"

    emit = root.find(".//ns:emit", ns)
    dest = root.find(".//ns:dest", ns)
    cnpj_emitente = apenas_numeros(emit.find("ns:CNPJ", ns).text) if emit is not None and emit.find("ns:CNPJ", ns) is not None else ""
    cnpj_destinatario = apenas_numeros(dest.find("ns:CNPJ", ns).text) if dest is not None and dest.find("ns:CNPJ", ns) is not None else ""
    cnpj_empresa = apenas_numeros(empresa.cnpj)

    if cnpj_emitente != cnpj_empresa and cnpj_destinatario != cnpj_empresa:
        return "cnpj_invalido"

    if modelo == "65":
        tipo_nota = "nfce"
    else:
        tipo_nota = "saida" if cnpj_emitente == cnpj_empresa else "entrada"

    icms_tot = root.find(".//ns:ICMSTot", ns)
    def get_decimal(tag):
        el = icms_tot.find(f"ns:{tag}", ns) if icms_tot is not None else None
        try:
            return Decimal(el.text) if el is not None else Decimal("0.00")
        except:
            return Decimal("0.00")

    data_emissao = datetime.fromisoformat(data_str.replace("Z", ""))

    # Criação da Nota (Mantido seu original)
    nf = NotaFiscal.objects.create(
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

    # NOVO: Salvar CFOPs da nota para o gráfico
    itens = root.findall(".//ns:det", ns)
    for item in itens:
        prod = item.find("ns:prod", ns)
        if prod is not None:
            cfop_v = prod.find("ns:CFOP", ns).text
            v_prod = Decimal(prod.find("ns:vProd", ns).text or "0.00")
            
            NotaFiscalCFOP.objects.create(
                empresa=empresa,
                nota=nf,
                cfop=cfop_v,
                valor=v_prod
            )

    return "salva"

# --- NOVAS FUNÇÕES PARA O DASHBOARD ---

def obter_metricas_dashboard(empresa, data_inicio=None, data_fim=None, tipo_nota=None):
    """Filtra e agrupa dados para os cards e gráficos."""
    qs = NotaFiscal.objects.filter(empresa=empresa)
    
    if data_inicio: qs = qs.filter(data_emissao__date__gte=data_inicio)
    if data_fim: qs = qs.filter(data_emissao__date__lte=data_fim)
    if tipo_nota: qs = qs.filter(tipo=tipo_nota)

    # Totais para os Cards
    totais = qs.aggregate(
        total_vendas=Sum('valor_total'),
        total_icms=Sum('valor_icms'),
        total_ipi=Sum('valor_ipi'),
        total_pis=Sum('valor_pis'),
        total_cofins=Sum('valor_cofins'),
        quantidade=Count('id')
    )

    # Dados para Gráfico CFOP (Soma valor por CFOP)
    cfops = NotaFiscalCFOP.objects.filter(nota__in=qs)\
        .values('cfop')\
        .annotate(total=Sum('valor'))\
        .order_by('-total')

    # Detecção de Furos (Sequência numérica)
    furos = identificar_furos(empresa, tipo_nota)

    # Info da última importação
    ultima_imp = UploadLote.objects.filter(empresa=empresa).order_by('-criado_em').first()

    return {
        "totais": totais,
        "cfops": cfops,
        "furos": furos,
        "ultima_importacao": ultima_imp,
    }

def identificar_furos(empresa, tipo_nota):
    """Verifica se há números faltando na sequência das notas."""
    if not tipo_nota: 
        return [] # Só faz sentido checar furo por tipo específico
    
    numeros = NotaFiscal.objects.filter(empresa=empresa, tipo=tipo_nota)\
        .values_list('numero', flat=True)
    
    if not numeros: return []
    
    # Converte para int para achar o gap
    nums = sorted([int(n) for n in numeros if n.isdigit()])
    if not nums: return []

    # Cria set do esperado vs real
    esperado = set(range(min(nums), max(nums) + 1))
    faltantes = esperado - set(nums)
    
    return sorted(list(faltantes))[:10] # Retorna os 10 primeiros furos