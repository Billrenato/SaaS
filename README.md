# Sistema SaaS de Processamento e Análise de Notas Fiscais (NFe / NFCe)

## Visão Geral

Este projeto é um sistema SaaS desenvolvido em Python com Django para processamento, validação e análise de arquivos XML de Notas Fiscais eletrônicas (NFe e NFCe).

O sistema permite que empresas realizem o upload de lotes de arquivos contendo notas fiscais em formato XML ou compactados (ZIP, RAR ou 7Z), processando automaticamente os documentos e armazenando as informações relevantes em banco de dados.

Após o processamento, o sistema disponibiliza métricas fiscais, análises de CFOP, identificação de inconsistências na numeração de notas e relatórios para apoio à gestão fiscal.

O objetivo principal da aplicação é automatizar o tratamento de grandes volumes de XML fiscais e fornecer insights úteis para empresas, contadores e áreas financeiras.

---

## Principais Funcionalidades

### Importação de Notas Fiscais

O sistema permite a importação de notas fiscais através de:

- Arquivos XML individuais
- Arquivos compactados (.zip)
- Arquivos compactados (.rar)
- Arquivos compactados (.7z)
- Diretórios contendo múltiplos XML

Durante a importação, o sistema:

- Extrai automaticamente arquivos compactados
- Localiza todos os XML presentes
- Processa cada documento individualmente
- Registra erros e inconsistências encontradas

---

### Validação de XML

Cada XML processado passa por uma série de validações:

- Estrutura XML válida
- Existência das tags obrigatórias
- Validação de autorização da SEFAZ
- Verificação de CNPJ emitente ou destinatário
- Identificação de duplicidade da nota
- Extração da chave da NFe

Notas que não passam nas validações são registradas como erro no lote de importação.

---

### Classificação Automática da Nota

O sistema identifica automaticamente o tipo da nota fiscal:

- **NFCe** (modelo 65)
- **Nota de Saída**
- **Nota de Entrada**

Essa classificação é baseada na comparação entre o CNPJ da empresa e os CNPJs presentes no XML.

---

### Extração de Dados Fiscais

Durante o processamento do XML, são extraídas informações relevantes como:

- Número da nota
- Chave da NFe
- Data de emissão
- Valor total da nota
- Valores de impostos
  - ICMS
  - IPI
  - PIS
  - COFINS
- Total de tributos

Esses dados são armazenados para posterior análise.

---

### Extração de Itens da Nota

Cada item da nota fiscal é processado individualmente.

Informações extraídas:

- Código do produto
- Descrição do produto
- NCM
- CEST
- Unidade de medida
- CFOP
- Valor do produto
- ICMS
- PIS
- COFINS

Esses dados permitem análises detalhadas sobre operações fiscais da empresa.

---

## Registro de Erros de Importação

Durante o processamento, erros são classificados e registrados no sistema.

Tipos de erro detectados:

- XML inválido
- CNPJ não pertence à empresa
- Nota duplicada
- Nota não autorizada pela SEFAZ

Esses erros ficam vinculados ao lote de importação para auditoria posterior.

---

## Processamento em Lote

O sistema suporta processamento de grandes volumes de XML através de upload de arquivos compactados.

Fluxo de processamento:

1. Upload do arquivo
2. Extração do conteúdo
3. Varredura recursiva de arquivos XML
4. Validação individual de cada nota
5. Armazenamento no banco de dados
6. Registro de erros encontrados
7. Geração de métricas de importação

Métricas retornadas após o processamento:

- Total de XML processados
- Notas salvas com sucesso
- XML inválidos
- Notas duplicadas
- CNPJ inválido
- Notas não autorizadas

---

## Dashboard e Métricas Fiscais

O sistema fornece métricas consolidadas das notas fiscais processadas.

Entre as principais métricas:

### Totais Financeiros

- Total de vendas
- Total de ICMS
- Total de IPI
- Total de PIS
- Total de COFINS
- Quantidade de notas emitidas

### Análise por CFOP

O sistema calcula o total de operações agrupadas por CFOP, permitindo identificar:

- Tipos de operação mais frequentes
- Distribuição de receitas por CFOP
- Análise fiscal das movimentações

---

## Identificação de Furos de Numeração

O sistema possui um mecanismo para detectar inconsistências na sequência de numeração das notas fiscais.

Essa funcionalidade identifica:

- Números de notas faltantes
- Possíveis erros de emissão
- Possíveis problemas fiscais

A verificação ocorre com base nas notas autorizadas registradas no sistema.

---

## Arquitetura do Projeto

Tecnologias utilizadas:

- Python
- Django
- PostgreSQL ou banco compatível
- XML ElementTree
- Bibliotecas de extração de arquivos

Bibliotecas utilizadas:

- zipfile
- rarfile
- py7zr
- xml.etree.ElementTree
- decimal
- logging
- tempfile
- shutil
- django ORM

---

## Estrutura do Processamento

O sistema é dividido em três grandes etapas:

### 1 - Extração

Responsável por abrir e extrair arquivos compactados.

Suporta:

- ZIP
- RAR
- 7Z
- XML direto
- Pastas

---

### 2 - Leitura do XML

Função responsável por:

- Interpretar o XML da NFe
- Validar estrutura
- Verificar autorização
- Identificar empresa participante
- Extrair dados fiscais

---

### 3 - Persistência no Banco

Após validação, os dados são salvos em modelos Django:

Principais modelos utilizados:

- NotaFiscal
- NotaFiscalCFOP
- UploadLote
- UploadErro

---

## Modelos de Dados

### NotaFiscal

Armazena dados principais da nota:

- empresa
- chave
- número
- data de emissão
- valores de impostos
- valor total
- tipo da nota
- status de autorização

---

### NotaFiscalCFOP

Armazena dados de itens da nota:

- produto
- descrição
- NCM
- CFOP
- valores
- impostos por item

---

### UploadLote

Representa um lote de importação contendo:

- arquivo enviado
- empresa
- data de upload

---

### UploadErro

Registra erros encontrados durante a importação:

- lote
- tipo de erro
- chave da nota

---

## Benefícios do Sistema

Automação de processamento fiscal  
Redução de trabalho manual com XML  
Centralização de notas fiscais  
Análise fiscal automatizada  
Identificação de inconsistências  
Escalabilidade para grandes volumes de notas  

---

## Possíveis Evoluções do Projeto

Integração com APIs da SEFAZ  
Dashboard avançado com gráficos  
Exportação de relatórios fiscais  
Integração com ERPs  
Monitoramento automático de notas emitidas  
Análise tributária avançada  

---

## Autor

Renato Junior Mathias

Analista e Desenvolvedor de Sistemas com foco em automação, análise de dados e desenvolvimento de soluções em Python.

LinkedIn  
www.linkedin.com/in/renato-jr-mathias-b76117221

---

## Licença

Este projeto é disponibilizado para fins de estudo, desenvolvimento e evolução de soluções fiscais baseadas em automação.
