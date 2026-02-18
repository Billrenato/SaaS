from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import UploadLote, NotaFiscal
from .services import processar_lote
from django.db.models import Sum


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
            messages.success(request, f"{resultado['salvas']} notas importadas com sucesso.")

        if resultado["cnpj_invalido"] > 0:
            messages.warning(request, f"{resultado['cnpj_invalido']} XML ignorados (CNPJ diferente da empresa).")

        if resultado["duplicadas"] > 0:
            messages.warning(request, f"{resultado['duplicadas']} XML duplicados.")

        if resultado["xml_invalido"] > 0:
            messages.warning(request, f"{resultado['xml_invalido']} XML inválidos.")

        return redirect("listar_notas")

    return render(request, "fiscal/upload.html")


@login_required
def listar_notas(request):
    # Queryset base filtrada pela empresa do usuário
    notas_qs = NotaFiscal.objects.filter(empresa=request.user.empresa).order_by("-data_emissao")

    # Estrutura para o Template organizar as Abas e Subabas
    notas_agrupadas = {
        'entrada': {},
        'saida': {},
        'nfce': {},
        'ultimas': notas_qs[:50]  # Histórico recente para a aba inicial
    }

    tipos = ['entrada', 'saida', 'nfce']

    for tipo in tipos:
        notas_tipo = notas_qs.filter(tipo=tipo)
        
        for nota in notas_tipo:
            # Chave de agrupamento por Mês e Ano (Ex: Janeiro / 2026)
            mes_ano = nota.data_emissao.strftime('%B / %Y').capitalize()
            
            if mes_ano not in notas_agrupadas[tipo]:
                notas_agrupadas[tipo][mes_ano] = {
                    'itens': [],
                    'total_valor': 0,
                    'total_impostos': 0
                }
            
            # Adiciona a nota à lista do mês específico
            notas_agrupadas[tipo][mes_ano]['itens'].append(nota)
            
            # Acumula os valores para o resumo do card
            notas_agrupadas[tipo][mes_ano]['total_valor'] += (nota.valor_total or 0)
            
            # Soma os campos de impostos cadastrados na model
            soma_impostos = (
                (nota.valor_icms or 0) + 
                (nota.valor_ipi or 0) + 
                (nota.valor_pis or 0) + 
                (nota.valor_cofins or 0) +
                (nota.valor_tributos or 0)
            )
            notas_agrupadas[tipo][mes_ano]['total_impostos'] += soma_impostos

    return render(request, "fiscal/listar_notas.html", {"notas_agrupadas": notas_agrupadas})