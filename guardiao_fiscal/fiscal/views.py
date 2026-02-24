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
from .services import processar_lote

@login_required
def upload_xml(request):
    if request.method == "POST":
        arquivo = request.FILES.get("arquivo")
        if not arquivo:
            messages.error(request, "Por favor, selecione um arquivo.")
            return render(request, "fiscal/upload.html")

        lote = UploadLote.objects.create(
            empresa=request.user.empresa,
            arquivo=arquivo
        )

        resultado = processar_lote(lote)

        # 🔥 salva listas na session para usar no modal
        request.session["erros_xml"] = {
            "cnpj_invalido": resultado["chaves_cnpj_invalido"],
            "duplicadas": resultado["chaves_duplicadas"],
            "xml_invalido": resultado["chaves_xml_invalido"],
            "nao_autorizada": resultado["chaves_nao_autorizada"],
        }

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
                f"{resultado['salvas']} notas importadas com sucesso de {resultado['total']} arquivos."
            )

        # =========================
        # ALERTAS ESPECÍFICOS
        # =========================
        if resultado["cnpj_invalido"] > 0:
            messages.warning(
                request,
                f"{resultado['cnpj_invalido']} XML ignorados (CNPJ diferente da empresa)."
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
                f"{resultado['nao_autorizada']} notas não autorizadas pela SEFAZ."
            )

        return render(request, "fiscal/upload.html")
    

    return render(request, "fiscal/upload.html")

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
            "descricao": f"Salto detectado: {', '.join(map(str, metricas['furos'][:10]))}"
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

def verificar_alertas(empresa):
    alertas = []
    
    # 1. Busca duplicidade por chave de acesso
    chaves_duplicadas = NotaFiscal.objects.filter(empresa=empresa)\
        .values('chave')\
        .annotate(qtd=Count('id'))\
        .filter(qtd__gt=1)

    if chaves_duplicadas.exists():
        total_duplicadas = chaves_duplicadas.count()
        # Pegamos as 3 primeiras chaves para exemplificar no alerta
        exemplo_chaves = ", ".join([c['chave'][-10:] for c in chaves_duplicadas[:3]])
        
        alertas.append({
            'tipo': 'Duplicidade de Chave',
            'numero': 'Crítico',
            'descricao': f'Existem {total_duplicadas} chaves de acesso duplicadas. Exemplos (finais): {exemplo_chaves}...'
        })
        
    return alertas


@login_required
def exportar_excel(request):
    empresa = request.user.empresa
    notas = NotaFiscal.objects.filter(empresa=empresa)

    # REPETIR OS FILTROS DA DASHBOARD
    tipo = request.GET.get('tipo')
    search = request.GET.get('search')
    ano = request.GET.get('ano')

    if tipo: notas = notas.filter(tipo=tipo)
    if ano: notas = notas.filter(data_emissao__year=ano)
    if search: notas = notas.filter(Q(chave__icontains=search) | Q(numero__icontains=search))

    # Selecionar campos para o Excel
    dados = notas.values('numero', 'chave', 'data_emissao', 'valor_total', 'tipo')
    df = pd.DataFrame(list(dados))
    
    if df.empty:
        messages.warning(request, "Não há dados para exportar com esses filtros.")
        return redirect('dashboard_relatorios')

    # Configurar Response
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename=relatorio_{datetime.date.today()}.xlsx'
    
    df.to_excel(response, index=False, engine='openpyxl')
    return response


from django.http import JsonResponse
from django.db.models import Sum, Count
from .models import NotaFiscal

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Count
from .models import NotaFiscal

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

    return JsonResponse({
        "numero": nota.numero,
        "data": nota.data_emissao.strftime("%d/%m/%Y %H:%M"),
        "total": float(nota.valor_total),
        "chave": nota.chave,
        # 🔥 IMPOSTOS
        "icms": float(nota.valor_icms),
        "ipi": float(nota.valor_ipi),
        "pis": float(nota.valor_pis),
        "cofins": float(nota.valor_cofins),
        "tributos": float(nota.valor_tributos),

        "resumo_cfop": resumo if resumo else []
    })

