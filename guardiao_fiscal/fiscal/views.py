import json
import pandas as pd
import datetime
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Sum, Count
from django.db.models.functions import TruncMonth
from .models import UploadLote, NotaFiscal
from .services import processar_lote,identificar_furos
from django.http import JsonResponse
from django.db.models import Sum, Count
from .models import NotaFiscal

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.db.models import Sum, Count
from .models import NotaFiscal
from django.http import HttpResponse
from openpyxl import Workbook
from .models import NotaFiscal

@login_required
def upload_xml(request):

    if request.method == "POST":

        arquivo = request.FILES.get("arquivo")

        if not arquivo:
            messages.error(request, "Por favor, selecione um arquivo.")
            return redirect("upload_xml")

        lote = UploadLote.objects.create(
            empresa=request.user.empresa,
            arquivo=arquivo
        )

        resultado = processar_lote(lote)

        # =========================
        # MENSAGEM PRINCIPAL
        # =========================
        if resultado["salvas"] == 0:
            messages.error(
                request,
                f"Nenhuma nota foi importada. "
                f"Total de arquivos: {resultado['total']}."
            )
        else:
            messages.success(
                request,
                f"{resultado['salvas']} notas importadas com sucesso "
                f"de {resultado['total']} arquivos."
            )

        # =========================
        # ALERTAS
        # =========================
        if resultado["cnpj_invalido"] > 0:
            messages.warning(
                request,
                f"{resultado['cnpj_invalido']} XML ignorados (CNPJ diferente)."
            )

        if resultado["duplicadas"] > 0:
            messages.warning(
                request,
                f"{resultado['duplicadas']} XML duplicados."
            )

        if resultado["xml_invalido"] > 0:
            messages.warning(
                request,
                f"{resultado['xml_invalido']} XML inválidos."
            )

        if resultado["nao_autorizada"] > 0:
            messages.warning(
                request,
                f"{resultado['nao_autorizada']} notas não autorizadas."
            )

        return redirect("upload")
    lotes = UploadLote.objects.filter(
        empresa=request.user.empresa
    ).order_by("-id")

    return render(request, "fiscal/upload.html", {
        "lotes": lotes
    })

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from .models import UploadLote, UploadErro

from django.db import models

@login_required
def historico_uploads(request):

    lotes = (
        UploadLote.objects
        .filter(empresa=request.user.empresa)
        .annotate(
            total_erros=Count("erros"),
            cnpj_invalido=Count("erros", filter=models.Q(erros__tipo="cnpj_invalido")),
            duplicada=Count("erros", filter=models.Q(erros__tipo="duplicada")),
            xml_invalido=Count("erros", filter=models.Q(erros__tipo="xml_invalido")),
            nao_autorizada=Count("erros", filter=models.Q(erros__tipo="nao_autorizada")),
        )
        .order_by("-id")
    )

    return render(request, "fiscal/historico_uploads.html", {
        "lotes": lotes
    })
@login_required
def listar_notas(request):
    notas_qs = NotaFiscal.objects.filter(empresa=request.user.empresa).order_by("-data_emissao")
    
    # IMPORTANTE: Use .iterator() ou limite a query se tiver milhares de notas
    # Aqui vamos agrupar de forma mais eficiente
    notas_agrupadas = {'entrada': {}, 'saida': {}, 'nfce': {}, 'ultimas': notas_qs[:50]}
    
    for nota in notas_qs:
        tipo = nota.tipo
        if tipo not in ['entrada', 'saida', 'nfce']: continue
        
        mes_ano = nota.data_emissao.strftime('%B / %Y').capitalize()
        
        if mes_ano not in notas_agrupadas[tipo]:
            notas_agrupadas[tipo][mes_ano] = {'itens': [], 'total_valor': 0, 'total_impostos': 0}
        
        notas_agrupadas[tipo][mes_ano]['itens'].append(nota)
        notas_agrupadas[tipo][mes_ano]['total_valor'] += float(nota.valor_total or 0)
        
        # Cálculo de impostos somados
        soma = sum([nota.valor_icms or 0, nota.valor_ipi or 0, nota.valor_pis or 0, 
                    nota.valor_cofins or 0, nota.valor_tributos or 0])
        notas_agrupadas[tipo][mes_ano]['total_impostos'] += float(soma)

    return render(request, "fiscal/listar_notas.html", {"notas_agrupadas": notas_agrupadas})

from django.db.models import Q # Importante para busca OU

import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from django.db.models.functions import TruncMonth
from .models import NotaFiscal
# Importe as funções que criamos no services.py
from .services import obter_metricas_dashboard 

from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import UploadErro


@login_required
def erros_lote(request, lote_id):
    lote = get_object_or_404(
        UploadLote,
        id=lote_id,
        empresa=request.user.empresa
    )

    erros = lote.erros.all()

    dados = {}

    for erro in erros:
        tipo = erro.get_tipo_display()  # 👈 pega o nome bonitinho do choices

        if tipo not in dados:
            dados[tipo] = []

        dados[tipo].append(erro.chave)

    return JsonResponse(dados)

@login_required
def dashboard_relatorios(request):
    empresa = request.user.empresa

    tipo = request.GET.get('tipo')
    search = request.GET.get('search')
    data_inicio = request.GET.get('data_inicio')
    data_fim = request.GET.get('data_fim')

    notas = NotaFiscal.objects.filter(empresa=empresa)

    if tipo:
        notas = notas.filter(tipo=tipo)

    if data_inicio:
        notas = notas.filter(data_emissao__date__gte=data_inicio)

    if data_fim:
        notas = notas.filter(data_emissao__date__lte=data_fim)

    if search:
        notas = notas.filter(
            Q(chave__icontains=search) |
            Q(numero__icontains=search)
        )

    # 📈 Evolução Mensal
    evolucao = notas.annotate(mes=TruncMonth('data_emissao')) \
        .values('mes') \
        .annotate(total=Sum('valor_total')) \
        .order_by('mes')

    labels_evolucao = [d['mes'].strftime('%b/%Y') for d in evolucao]
    valores_evolucao = [float(d['total']) for d in evolucao]

    # 🔥 Métricas centralizadas
    metricas = obter_metricas_dashboard(
        empresa,
        data_inicio=data_inicio,
        data_fim=data_fim,
        tipo_nota=tipo
    )

    t = metricas['totais']

    # 📊 CFOP
    labels_cfop = [c['cfop'] for c in metricas['cfops']]
    valores_cfop = [float(c['total']) for c in metricas['cfops']]

    # 📊 Impostos (agora com total geral também)
    total_icms = float(t['total_icms'] or 0)
    total_ipi = float(t['total_ipi'] or 0)
    total_pis = float(t['total_pis'] or 0)
    total_cofins = float(t['total_cofins'] or 0)

    total_impostos_geral = total_icms + total_ipi + total_pis + total_cofins

    labels_impostos = ['ICMS', 'IPI', 'PIS', 'COFINS']
    valores_impostos = [total_icms, total_ipi, total_pis, total_cofins]

    # 🚨 Inconsistências para modal

    inconsistencias = []

    if metricas['furos']:
        inconsistencias.append({
            "tipo": "Furo de Numeração",
            "descricao": f"Foram encontrados {len(metricas['furos'])} furos na sequência de notas.",
            "lista": metricas['furos']  # 👈 passa TODOS
        })

    duplicadas = NotaFiscal.objects.filter(empresa=empresa) \
        .values('chave') \
        .annotate(qtd=Count('id')) \
        .filter(qtd__gt=1) \
        .count()

    if duplicadas > 0:
        inconsistencias.append({
            "tipo": "Notas Duplicadas",
            "descricao": f"{duplicadas} chaves duplicadas encontradas."
        })

    context = {
        # Empresa
        "empresa_nome": empresa.nome,
        "empresa_cnpj": empresa.cnpj,

        # Gráficos
        'labels_evolucao': json.dumps(labels_evolucao),
        'valores_evolucao': json.dumps(valores_evolucao),
        'labels_cfop': json.dumps(labels_cfop),
        'valores_cfop': json.dumps(valores_cfop),
        'labels_impostos': json.dumps(labels_impostos),
        'valores_impostos': json.dumps(valores_impostos),

        # Cards
        'mes_atual_valor': t['total_vendas'] or 0,
        'total_notas': t['quantidade'] or 0,
        'total_impostos_geral': total_impostos_geral,

        # Filtros
        'filter_tipo': tipo,
        'filter_search': search,
        'filter_data_inicio': data_inicio,
        'filter_data_fim': data_fim,

        # Auditoria
        'furos': metricas['furos'],
        'ultima_importacao': metricas['ultima_importacao'],
        'inconsistencias': inconsistencias,
    }

    return render(request, "fiscal/relatorios.html", context)

from django.db.models import Count

def verificar_alertas(empresa):
    alertas = []

    # =========================
    # 1. DUPLICIDADE DE CHAVE
    # =========================
    chaves_duplicadas = (
        NotaFiscal.objects
        .filter(empresa=empresa)
        .values('chave')
        .annotate(qtd=Count('id'))
        .filter(qtd__gt=1)
    )

    if chaves_duplicadas.exists():
        total_duplicadas = chaves_duplicadas.count()
        exemplo_chaves = ", ".join([c['chave'][-10:] for c in chaves_duplicadas[:3]])

        alertas.append({
            'tipo': 'Duplicidade de Chave',
            'numero': 'Crítico',
            'descricao': f'Existem {total_duplicadas} chaves duplicadas. Ex: {exemplo_chaves}'
        })

    # =========================
    # 2. FUROS DE NUMERAÇÃO
    # =========================
    furos = identificar_furos(empresa, "saida")

    if furos:
        alertas.append({
            "tipo": "Furo de Numeração",
            "numero": "Alerta",
            "descricao": f"Foram encontrados {len(furos)} furos na sequência de notas."
        })

    return alertas

import urllib.parse

@login_required
def exportar_excel(request, tipo, mes):
    """
    Exporta notas fiscais por tipo e mês para Excel
    URL esperada: /exportar-excel/<tipo>/<mes>/
    Ex: /exportar-excel/nfce/february-2026/
    """

    # 🔹 Trata o mês vindo da URL (ex: february-2026)
    mes = mes.replace('-', ' ')   # february 2026
    mes = mes.title()             # February 2026

    # 🔹 Separa mês e ano
    try:
        nome_mes, ano = mes.split()
        ano = int(ano)
    except Exception:
        return HttpResponse("Formato de mês inválido", status=400)

    # 🔹 Mapeamento mês → número
    meses_map = {
        "January": 1, "February": 2, "March": 3,
        "April": 4, "May": 5, "June": 6,
        "July": 7, "August": 8, "September": 9,
        "October": 10, "November": 11, "December": 12
    }

    mes_num = meses_map.get(nome_mes)

    if not mes_num:
        return HttpResponse("Mês inválido", status=400)

    # 🔹 Filtra notas corretamente
    notas = NotaFiscal.objects.filter(
        tipo=tipo,
        data_emissao__month=mes_num,
        data_emissao__year=ano,
        empresa=request.user.empresa  # 🔥 IMPORTANTE (segurança multi-tenant)
    )

    # 🔹 Cria o Excel
    wb = Workbook()
    ws = wb.active
    ws.title = f"{tipo.upper()} {nome_mes}-{ano}"

    # 🔹 Cabeçalho
    ws.append([
        "Número",
        "Data",
        "CNPJ",
        "Valor Total"
    ])

    # 🔹 Dados
    for n in notas:
        ws.append([
            n.numero,
            n.data_emissao.strftime("%d/%m/%Y") if n.data_emissao else "",
            getattr(n, "cnpj_emitente", ""),
            float(n.valor_total or 0)
        ])

    # 🔹 Resposta HTTP (download)
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

    response['Content-Disposition'] = (
        f'attachment; filename="notas_{tipo}_{ano}_{mes_num}.xlsx"'
    )

    wb.save(response)
    return response


def nota_detalhes(request, pk):

    nota = get_object_or_404(
        NotaFiscal.objects.prefetch_related("cfops"),
        pk=pk
    )

    cfops = (
        nota.cfops
        .values("cfop")
        .annotate(
            total=Count("id"),
            valor_total=Sum("valor")
        )
        .order_by("cfop")
    )

    resumo = [
        f"{c['cfop']} ({c['total']}x) - R$ {c['valor_total']}"
        for c in cfops
    ]

    # 🔥 ITENS (PRODUTOS COM IMPOSTOS)
    itens = list(
        nota.cfops.values(
            "cod_prod",
            "descricao",
            "ncm",
            "cest",
            "cfop",
            "valor",
            "icms_cst",
            "icms_valor",
            "pis_cst",
            "pis_valor",
            "cofins_cst",
            "cofins_valor",
        )
    )

    return JsonResponse({
        "numero": nota.numero,
        "data": nota.data_emissao.strftime("%d/%m/%Y %H:%M"),
        "total": float(nota.valor_total),
        "chave": nota.chave,

        # 🔥 IMPOSTOS DA NOTA
        "icms": float(nota.valor_icms),
        "ipi": float(nota.valor_ipi),
        "pis": float(nota.valor_pis),
        "cofins": float(nota.valor_cofins),
        "tributos": float(nota.valor_tributos),

        # 🔥 CFOP
        "resumo_cfop": resumo if resumo else [],

        # 🔥 ITENS
        "itens": itens
    })