from django.urls import path
from . import views
# Importando todas as views necessárias do arquivo views.py atual
from .views import (
    upload_xml, 
    listar_notas, 
    dashboard_relatorios, 
    exportar_excel,
    nota_detalhes,
    erros_lote,
    historico_uploads
)

urlpatterns = [
    # Rota para o upload de arquivos (XML, ZIP, RAR)
    path("upload/", upload_xml, name="upload"),
    
    # Rota para a listagem tabular e histórico de notas
    path("notas/", listar_notas, name="listar_notas"),
    
    # Rota para o Painel de BI / Gráficos
    path("relatorios/", dashboard_relatorios, name="dashboard_relatorios"),
    
    # Rota funcional para gerar e baixar o arquivo Excel
    path("relatorios/exportar/", exportar_excel, name="exportar_excel"),
    path("nota/<int:pk>/detalhes/", nota_detalhes, name="nota_detalhes"),
    path("erros-lote/<int:lote_id>/", erros_lote, name="erros_lote"),
    path("historico-uploads/", historico_uploads, name="historico_uploads"),
    
]