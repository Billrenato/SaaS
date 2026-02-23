from django.db import models
from accounts.models import Empresa


class NotaFiscal(models.Model):

    TIPOS = [
        ("entrada", "Entrada"),
        ("saida", "Saída"),
        ("nfce", "NFC-e"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    chave = models.CharField(max_length=44, unique=True)
    numero = models.CharField(max_length=20)
    data_emissao = models.DateTimeField()
    autorizada = models.BooleanField(default=True)
    valor_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    valor_tributos = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    valor_icms = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    valor_ipi = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    valor_pis = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    valor_cofins = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    tipo = models.CharField(max_length=10, choices=TIPOS)

    criada_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.numero} - {self.tipo}"

class NotaFiscalCFOP(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    nota = models.ForeignKey(NotaFiscal, on_delete=models.CASCADE, related_name="cfops")

    cfop = models.CharField(max_length=10)
    descricao = models.CharField(max_length=255, blank=True, null=True)

    valor = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["empresa", "cfop"]),
        ]

    def __str__(self):
        return f"{self.cfop} - {self.valor}"

class UploadLote(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    criado_em = models.DateTimeField(auto_now_add=True)
    arquivo = models.FileField(upload_to="uploads/")

    def __str__(self):
        return f"Lote {self.id} - {self.empresa}"
