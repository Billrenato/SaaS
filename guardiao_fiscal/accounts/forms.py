from django import forms  # O erro estava aqui, remova o 'from django import college'
from django.contrib.auth.forms import UserCreationForm
from .models import User

class RegistroForm(UserCreationForm):
    email = forms.EmailField(required=True)
    nome_empresa = forms.CharField(max_length=255, label="Nome da Empresa")
    cnpj = forms.CharField(max_length=14, label="CNPJ (Somente números)")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "nome_empresa", "cnpj")