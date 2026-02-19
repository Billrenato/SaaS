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

@login_required
def dashboard_relatorios(request):
    empresa = request.user.empresa
    notas = NotaFiscal.objects.filter(empresa=empresa)

    # --- Captura dos Filtros do GET ---
    tipo = request.GET.get('tipo')
    ano = request.GET.get('ano')
    search = request.GET.get('search')

    # --- Aplicação dos Filtros ---
    if tipo:
        notas = notas.filter(tipo=tipo)
    
    if ano:
        # Garante que o ano seja um número para o filtro de data
        notas = notas.filter(data_emissao__year=ano)
        
    if search:
        # O uso do Q permite buscar em múltiplos campos com "OU"
        notas = notas.filter(
            Q(chave__icontains=search) | Q(numero__icontains=search)
        )

    # --- Lógica do Gráfico (Reflete os filtros acima) ---
    evolucao = notas.annotate(mes=TruncMonth('data_emissao')) \
        .values('mes') \
        .annotate(total=Sum('valor_total')) \
        .order_by('mes')

    labels_evolucao = [d['mes'].strftime('%b/%Y') for d in evolucao]
    valores_evolucao = [float(d['total']) for d in evolucao]

    # --- Cálculo do Valor Total (Baseado no Filtro Atual) ---
    valor_total_filtrado = notas.aggregate(total=Sum('valor_total'))['total'] or 0

    context = {
        'labels_evolucao': json.dumps(labels_evolucao),
        'valores_evolucao': json.dumps(valores_evolucao),
        'mes_atual_valor': valor_total_filtrado,
        'total_notas': notas.count(),
        'filter_tipo': tipo,
        'filter_search': search,
        'alertas': verificar_alertas(empresa)
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