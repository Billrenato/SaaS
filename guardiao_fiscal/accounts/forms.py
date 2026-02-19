from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Empresa  # Importa o modelo Empresa para validar o CNPJ

class RegistroForm(UserCreationForm):
    email = forms.EmailField(required=True)
    nome_empresa = forms.CharField(max_length=255)
    cnpj = forms.CharField(max_length=18)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ("email",)

    def clean_cnpj(self):
        cnpj = self.cleaned_data.get('cnpj')
        if Empresa.objects.filter(cnpj=cnpj).exists():
            raise forms.ValidationError("Este CNPJ já está cadastrado.")
        return cnpj