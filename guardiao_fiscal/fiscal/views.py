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

        if resultado["salvas"] == 0:
            messages.error(request, "Nenhuma nota foi importada.")
        else:
            messages.success(request, f"{resultado['salvas']} notas importadas.")

        # Exibe alertas se houver problemas específicos
        if resultado.get("cnpj_invalido"): messages.warning(request, f"{resultado['cnpj_invalido']} CNPJs inválidos.")
        if resultado.get("duplicadas"): messages.warning(request, f"{resultado['duplicadas']} duplicadas.")
        
        return redirect("listar_notas")
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
    
    # --- Captura dos Filtros do GET ---
    tipo = request.GET.get('tipo')
    search = request.GET.get('search')
    data_inicio = request.GET.get('data_inicio') # Novo
    data_fim = request.GET.get('data_fim')       # Novo

    # --- Base de Notas (QuerySet) ---
    notas = NotaFiscal.objects.filter(empresa=empresa)

    # --- Aplicação dos Filtros ---
    if tipo:
        notas = notas.filter(tipo=tipo)
    
    if data_inicio:
        notas = notas.filter(data_emissao__date__gte=data_inicio)
    
    if data_fim:
        notas = notas.filter(data_emissao__date__lte=data_fim)
        
    if search:
        notas = notas.filter(
            Q(chave__icontains=search) | Q(numero__icontains=search)
        )

    # --- Gráfico de Evolução Mensal (Mantido) ---
    evolucao = notas.annotate(mes=TruncMonth('data_emissao')) \
        .values('mes') \
        .annotate(total=Sum('valor_total')) \
        .order_by('mes')

    labels_evolucao = [d['mes'].strftime('%b/%Y') for d in evolucao]
    valores_evolucao = [float(d['total']) for d in evolucao]

    # --- NOVAS MÉTRICAS (CFOP, Impostos e Alertas) ---
    # Chamamos o service passando os filtros atuais para sincronizar os gráficos
    metricas = obter_metricas_dashboard(
        empresa, 
        data_inicio=data_inicio, 
        data_fim=data_fim, 
        tipo_nota=tipo
    )

    # Preparação para Gráfico de CFOP
    labels_cfop = [c['cfop'] for c in metricas['cfops']]
    valores_cfop = [float(c['total']) for c in metricas['cfops']]

    # Preparação para Gráfico de Impostos (Pizza/Rosca)
    t = metricas['totais']
    labels_impostos = ['ICMS', 'IPI', 'PIS', 'COFINS']
    valores_impostos = [
        float(t['total_icms'] or 0),
        float(t['total_ipi'] or 0),
        float(t['total_pis'] or 0),
        float(t['total_cofins'] or 0)
    ]

    

    context = {
        # Gráficos
        'labels_evolucao': json.dumps(labels_evolucao),
        'valores_evolucao': json.dumps(valores_evolucao),
        'labels_cfop': json.dumps(labels_cfop),
        'valores_cfop': json.dumps(valores_cfop),
        'labels_impostos': json.dumps(labels_impostos),
        'valores_impostos': json.dumps(valores_impostos),
        
        # Cards e Totais
        'mes_atual_valor': t['total_vendas'] or 0,
        'total_notas': t['quantidade'] or 0,
        
        # Filtros (para persistir nos inputs da tela)
        'filter_tipo': tipo,
        'filter_search': search,
        'filter_data_inicio': data_inicio,
        'filter_data_fim': data_fim,
        
        # Alertas e Auditoria
        'furos': metricas['furos'],
        'ultima_importacao': metricas['ultima_importacao'],
    }
    
    return render(request, "fiscal/relatorios.html", context)

def verificar_alertas(empresa):
    alertas = []
    # Busca duplicidade por chave de acesso
    duplicadas_count = NotaFiscal.objects.filter(empresa=empresa)\
        .values('chave').annotate(qtd=Count('id')).filter(qtd__gt=1).count()
    
    if duplicadas_count > 0:
        alertas.append(f"Atenção: Existem {duplicadas_count} notas com chaves duplicadas no sistema.")
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