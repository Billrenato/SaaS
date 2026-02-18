from django.shortcuts import render, redirect
from django.contrib.auth import login
from .forms import RegistroForm # Vamos criar este form abaixo
from django.db import transaction

def registro(request):
    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                # Salva o usuário
                user = form.save()
                # Cria a empresa vinculada
                from .models import Empresa
                Empresa.objects.create(
                    cnpj=form.cleaned_data.get('cnpj'),
                    nome=form.cleaned_data.get('nome_empresa'),
                    user=user
                )
                login(request, user)
                return redirect('listar_notas')
    else:
        form = RegistroForm()
    return render(request, 'accounts/registro.html', {'form': form})