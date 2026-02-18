

# Create your views here.
from django.shortcuts import render, redirect
from .models import UploadLote
from django.contrib.auth.decorators import login_required





from .services import processar_lote

@login_required
def upload_xml(request):
    if request.method == "POST":
        lote = UploadLote.objects.create(
            empresa=request.user.empresa,
            arquivo=request.FILES['arquivo']
        )
        processar_lote(lote)
        return redirect("upload")

    return render(request, "upload.html")



from .models import NotaFiscal

@login_required
def listar_notas(request):
    empresa = request.user.empresa
    notas = NotaFiscal.objects.filter(empresa=empresa).order_by('-data_emissao')

    return render(request, "fiscal/listar_notas.html", {
        "notas": notas
    })