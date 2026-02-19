from django.db import models
from django.contrib.auth.models import User

class Empresa(models.Model):
    # OneToOneField é melhor que ForeignKey aqui, pois cada usuário 
    # terá apenas UMA empresa no seu SaaS.
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    nome = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=18, unique=True)

    def __str__(self):
        return f"{self.nome} ({self.cnpj})"