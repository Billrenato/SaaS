from django.shortcuts import render, redirect
from django.contrib import messages  # Importante para exibir o aviso de sucesso
from django.db import transaction
from .forms import RegistroForm
from .models import Empresa # Boa prática importar no topo

def registro(request):
    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # 1. Salva o usuário (mas não faz o login automático)
                    user = form.save()
                    
                    # 2. Cria a empresa vinculada
                    Empresa.objects.create(
                        cnpj=form.cleaned_data.get('cnpj'),
                        nome=form.cleaned_data.get('nome_empresa'),
                        user=user
                    )
                    
                    # 3. Adiciona a mensagem de sucesso que aparecerá na próxima tela
                    messages.success(request, "Conta criada com sucesso! Agora você já pode fazer o login.")
                    
                    # 4. Redireciona para o login em vez de listar_notas
                    return redirect('login') 
                
            except Exception as e:
                # Caso algo dê errado na transação, adicionamos um erro
                messages.error(request, "Erro ao criar conta. Verifique os dados e tente novamente.")
    else:
        form = RegistroForm()
        
    return render(request, 'accounts/registro.html', {'form': form})