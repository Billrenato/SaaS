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
from .models import UploadErro

logger = logging.getLogger(__name__)

def apenas_numeros(valor):
    return re.sub(r'\D', '', str(valor))
def processar_lote(upload_lote):

    # 🔥 limpa erros antigos se reprocessar o mesmo lote
    UploadErro.objects.filter(lote=upload_lote).delete()

    caminho = upload_lote.arquivo.path
    empresa = upload_lote.empresa
    pasta_temp = tempfile.mkdtemp()

    resultado = {
        "salvas": 0,
        "cnpj_invalido": 0,
        "duplicadas": 0,
        "xml_invalido": 0,
        "nao_autorizada": 0,
        "total": 0,
    }

    try:
        # ======================
        # EXTRAÇÃO
        # ======================
        if caminho.lower().endswith(".7z"):
            with py7zr.SevenZipFile(caminho, mode='r') as archive:
                archive.extractall(path=pasta_temp)

        elif caminho.lower().endswith(".zip"):
            with zipfile.ZipFile(caminho, 'r') as zip_ref:
                zip_ref.extractall(path=pasta_temp)

        elif caminho.lower().endswith(".rar"):
            with rarfile.RarFile(caminho) as rar_ref:
                rar_ref.extractall(path=pasta_temp)

        elif caminho.lower().endswith(".xml"):
            shutil.copy(caminho, pasta_temp)

        elif os.path.isdir(caminho):
            shutil.copytree(caminho, pasta_temp, dirs_exist_ok=True)

        else:
            raise Exception("Formato de arquivo não suportado.")

        # ======================
        # VARREDURA
        # ======================
        for raiz, _, arquivos in os.walk(pasta_temp):
            for nome in arquivos:
                if nome.lower().endswith(".xml"):

                    resultado["total"] += 1
                    caminho_xml = os.path.join(raiz, nome)

                    try:
                        with open(caminho_xml, 'rb') as f:
                            xml_bytes = f.read()

                        status = ler_xml(xml_bytes, empresa)

                        # 🔥 extrair chave da NFe
                        chave = "XML comprometido"
                        try:
                            root = ET.fromstring(xml_bytes)
                            infNFe = root.find(".//{http://www.portalfiscal.inf.br/nfe}infNFe")
                            if infNFe is not None:
                                chave = infNFe.attrib.get("Id", "").replace("NFe", "")
                        except:
                            pass

                        # ======================
                        # STATUS
                        # ======================
                        if status == "salva":
                            resultado["salvas"] += 1

                        elif status == "cnpj_invalido":
                            resultado["cnpj_invalido"] += 1
                            UploadErro.objects.create(
                                lote=upload_lote,
                                tipo="cnpj_invalido",
                                chave=chave
                            )

                        elif status == "duplicada":
                            resultado["duplicadas"] += 1
                            UploadErro.objects.create(
                                lote=upload_lote,
                                tipo="duplicada",
                                chave=chave
                            )

                        elif status == "xml_invalido":
                            resultado["xml_invalido"] += 1
                            UploadErro.objects.create(
                                lote=upload_lote,
                                tipo="xml_invalido",
                                chave=chave
                            )

                        elif status == "nao_autorizada":
                            resultado["nao_autorizada"] += 1
                            UploadErro.objects.create(
                                lote=upload_lote,
                                tipo="nao_autorizada",
                                chave=chave
                            )

                    except Exception as e:
                        logger.error(f"Erro no XML {nome}: {e}")

                        resultado["xml_invalido"] += 1

                        UploadErro.objects.create(
                            lote=upload_lote,
                            tipo="xml_invalido",
                            chave=nome
                        )

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

    # ======================
    # AUTORIZAÇÃO
    # ======================
    prot = root.find(".//ns:protNFe/ns:infProt", ns)
    autorizada = False

    if prot is not None:
        cstat = prot.find("ns:cStat", ns)
        if cstat is not None and cstat.text == "100":
            autorizada = True

    if not autorizada:
        return "nao_autorizada"

    # ======================
    # CNPJ
    # ======================
    emit = root.find(".//ns:emit", ns)
    dest = root.find(".//ns:dest", ns)

    cnpj_emitente = apenas_numeros(
        emit.find("ns:CNPJ", ns).text
    ) if emit is not None and emit.find("ns:CNPJ", ns) is not None else ""

    cnpj_destinatario = apenas_numeros(
        dest.find("ns:CNPJ", ns).text
    ) if dest is not None and dest.find("ns:CNPJ", ns) is not None else ""

    cnpj_empresa = apenas_numeros(empresa.cnpj)

    if cnpj_emitente != cnpj_empresa and cnpj_destinatario != cnpj_empresa:
        return "cnpj_invalido"

    # ======================
    # DUPLICIDADE (SÓ AGORA)
    # ======================
    if NotaFiscal.objects.filter(chave=chave, empresa=empresa).exists():
        return "duplicada"

    # ======================
    # TIPO
    # ======================
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
        tipo=tipo_nota,
        autorizada=True
    )

    # ======================
    # CFOP
    # ======================
    itens = root.findall(".//ns:det", ns)

    for item in itens:
        prod = item.find("ns:prod", ns)
        imposto = item.find("ns:imposto", ns)

        if prod is not None:
            codprod = prod.find("ns:cProd", ns).text
            un_med = prod.find("ns:uCom", ns).text
            descri = prod.find("ns:xProd", ns).text
            prod_cest = prod.findtext("ns:CEST", default=None, namespaces=ns)
            prod_ncm = prod.find("ns:NCM", ns).text
            cfop_v = prod.find("ns:CFOP", ns).text
            v_prod = Decimal(prod.find("ns:vProd", ns).text or "0.00")

            # ===== ICMS =====
            icms_cst = None
            icms_valor = Decimal("0.00")

            icms = imposto.find("ns:ICMS", ns)
            if icms is not None:
                icms_tipo = list(icms)[0]  # ICMSSN102, ICMS00, etc
                icms_cst = icms_tipo.findtext("ns:CSOSN", default=None, namespaces=ns) or \
                        icms_tipo.findtext("ns:CST", default=None, namespaces=ns)
                icms_valor = Decimal(icms_tipo.findtext("ns:vICMS", default="0.00", namespaces=ns))

            # ===== PIS =====
            pis = imposto.find("ns:PIS", ns)
            pis_tipo = list(pis)[0] if pis is not None else None
            pis_cst = pis_tipo.findtext("ns:CST", default=None, namespaces=ns) if pis_tipo else None
            pis_valor = Decimal(pis_tipo.findtext("ns:vPIS", default="0.00", namespaces=ns)) if pis_tipo else Decimal("0.00")

            # ===== COFINS =====
            cofins = imposto.find("ns:COFINS", ns)
            cofins_tipo = list(cofins)[0] if cofins is not None else None
            cofins_cst = cofins_tipo.findtext("ns:CST", default=None, namespaces=ns) if cofins_tipo else None
            cofins_valor = Decimal(cofins_tipo.findtext("ns:vCOFINS", default="0.00", namespaces=ns)) if cofins_tipo else Decimal("0.00")

            NotaFiscalCFOP.objects.create(
                empresa=empresa,
                cod_prod=codprod,
                descricao=descri,
                ncm=prod_ncm,
                nota=nf,
                cfop=cfop_v,
                valor=v_prod,
                un=un_med,

                icms_cst=icms_cst,
                icms_valor=icms_valor,
                pis_cst=pis_cst,
                pis_valor=pis_valor,
                cofins_cst=cofins_cst,
                cofins_valor=cofins_valor,
            )

    return "salva"

# --- NOVAS FUNÇÕES PARA O DASHBOARD ---

def obter_metricas_dashboard(empresa, data_inicio=None, data_fim=None, tipo_nota=None):
    qs = NotaFiscal.objects.filter(empresa=empresa)
    
    if data_inicio:
        qs = qs.filter(data_emissao__date__gte=data_inicio)

    if data_fim:
        qs = qs.filter(data_emissao__date__lte=data_fim)

    if tipo_nota:
        qs = qs.filter(tipo=tipo_nota)

    # Totais
    totais = qs.aggregate(
        total_vendas=Sum('valor_total'),
        total_icms=Sum('valor_icms'),
        total_ipi=Sum('valor_ipi'),
        total_pis=Sum('valor_pis'),
        total_cofins=Sum('valor_cofins'),
        quantidade=Count('id')
    )

    # CFOP
    cfops = (
        NotaFiscalCFOP.objects
        .filter(nota__in=qs)
        .values('cfop')
        .annotate(total=Sum('valor'))
        .order_by('-total')
    )

    # ✅ AQUI está o conserto
    furos = identificar_furos(
        empresa,
        tipo_nota,
        data_inicio=data_inicio,
        data_fim=data_fim
    )

    ultima_imp = UploadLote.objects.filter(empresa=empresa).order_by('-criado_em').first()

    return {
        "totais": totais,
        "cfops": cfops,
        "furos": furos,
        "ultima_importacao": ultima_imp,
    }
def identificar_furos(empresa, tipo_nota, data_inicio=None, data_fim=None):
    if not tipo_nota:
        return []

    qs = NotaFiscal.objects.filter(
        empresa=empresa,
        tipo=tipo_nota,
        autorizada=True
    ).exclude(numero__isnull=True).exclude(numero="")

    if data_inicio:
        qs = qs.filter(data_emissao__date__gte=data_inicio)

    if data_fim:
        qs = qs.filter(data_emissao__date__lte=data_fim)

    notas = qs.values_list("numero", flat=True)

    numeros = []
    for n in notas:
        try:
            numeros.append(int(n))
        except (ValueError, TypeError):
            continue

    if len(numeros) < 2:
        return []

    numeros.sort()

    inconsistencias = []
    anterior = numeros[0]

    for atual in numeros[1:]:
        if atual > anterior + 1:
            for f in range(anterior + 1, atual):
                inconsistencias.append(f)
        anterior = atual

    return inconsistencias