# Looper Reports: Motor de Geração de Relatórios de Performance com IA

---

![Python](https://img.shields.io/badge/Python-3.12%2B-blue?style=for-the-badge&logo=python) ![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-green?style=for-the-badge&logo=fastapi) ![Docker](https://img.shields.io/badge/Docker-20.10%2B-blue?style=for-the-badge&logo=docker) ![MongoDB](https://img.shields.io/badge/MongoDB-4.4%2B-green?style=for-the-badge&logo=mongodb) ![Google Gemini](https://img.shields.io/badge/Google%20Gemini-blue?style=for-the-badge&logo=google)

## 1. Sobre o Projeto

O **Looper Reports** é um sistema de back-end projetado para automatizar a criação de relatórios de progresso semanais para alunos de coaching de alta performance. O sistema consome dados brutos de check-ins (nutrição, sono, treinos) e os transforma em um relatório HTML detalhado, estilizado e repleto de insights, utilizando o **Google Gemini** através do **LangChain** para análise e geração de texto.

O objetivo principal é liberar o coach do trabalho manual de compilação e análise de dados, permitindo que ele se concentre na estratégia e no relacionamento com o aluno, ao mesmo tempo que entrega um produto de altíssima qualidade e valor percebido.

### 1.1. Funcionalidades Principais

- **Geração de Relatório via API:** Um único endpoint que orquestra todo o processo.
- **Análise de Múltiplas Fontes:** Agrega dados de check-ins diários, metas de longo prazo e relatórios anteriores.
- **Motor de IA com Contexto Encadeado:** Utiliza um padrão de Orquestrador-Agente. O conteúdo gerado em cada etapa é adicionado ao contexto da etapa seguinte, permitindo análises mais profundas e coesas.
- **Geração Baseada em Prompts:** A lógica de geração de cada seção é definida em arquivos de prompt de texto, permitindo fácil iteração e ajuste fino sem alterar o código.
- **Template HTML:** O relatório final é montado a partir de um template, garantindo consistência visual.

---

## 2. Arquitetura e Fluxo de Dados

O sistema foi desenhado com foco em modularidade, utilizando um padrão de **Orquestrador-Agente**.

### 2.1. Componentes

1.  **API (FastAPI):**
    -   Expõe o endpoint principal (`/api/v1/reports/generate/{student_id}`) que dispara a geração do relatório.
    -   Responsável pela validação da requisição e por injetar as dependências (como a conexão com o banco de dados).

2.  **Orquestrador (`ReportService`):
    -   É o cérebro do sistema. Ao ser chamado pela API, ele executa as seguintes etapas:
        1.  **Coleta de Dados:** Busca no MongoDB todos os dados relevantes para a semana do aluno.
        2.  **Construção de Contexto:** Processa os dados brutos, criando um "contexto base" que será o alicerce para as chamadas de IA.
        3.  **Coordenação de Agentes:** Invoca o `ReportGeneratorAgent` sequencialmente para cada seção. A cada seção gerada, o contexto é enriquecido com o novo conteúdo.
        4.  **Montagem do HTML:** Insere o conteúdo gerado por cada agente no template HTML principal.
        5.  **Persistência:** Salva o relatório HTML final no banco de dados.

3.  **Agente (`ReportGeneratorAgent`):
    -   Um agente especializado que interage com o LLM (Google Gemini) via LangChain.
    -   Recebe o **tipo de seção** e o **contexto** (que vai sendo enriquecido a cada passo).
    -   Carrega o **prompt específico** para a seção solicitada (`app/agents/prompts/sections/`).
    -   Formata o prompt final e o envia para o LLM.
    -   Retorna o texto (HTML) gerado para o orquestrador.

### 2.2. Fluxo de Dados

```mermaid
graph TD
    A[Requisição HTTP POST /api/v1/reports/generate/{student_id}] --> B{API - FastAPI};
    B --> C{Orquestrador - ReportService};
    C --> D[1. Coleta Dados no MongoDB];
    D --> E[2. Monta Contexto Base];
    E --> F{3. Gera Seção 1 com Agente};
    F --> G[LLM - Google Gemini];
    G --> F;
    F --> H[4. Adiciona Seção 1 ao Contexto];
    H --> I{5. Gera Seção 2 com Agente};
    I --> G;
    G --> I;
    I --> J[... Continua para todas as seções ...];
    J --> K[6. Monta HTML Final];
    K --> L[7. Salva Relatório no MongoDB];
    L --> C;
    C --> B;
    B --> M[Retorna HTML do Relatório];
```

---

## 3. Tecnologias Utilizadas

- **Back-end:** Python 3.12
- **Framework API:** FastAPI
- **Banco de Dados:** MongoDB (com `motor` para operações assíncronas)
- **IA & LLM:** 
    - **Modelo:** Google Gemini Pro
    - **Framework:** LangChain (`langchain`, `langchain-google-genai`)
- **Containerização:** Docker & Docker Compose
- **Análise de Dados:** `numpy`
- **Testes:** `pytest` e `pytest-asyncio`

---

## 4. Guia de Instalação e Execução

### 4.1. Pré-requisitos

- Docker e Docker Compose instalados.
- Python 3.12+ e `pip`.
- Acesso a uma chave de API do Google Gemini.

### 4.2. Configuração do Ambiente

1.  **Clone o repositório:**
    ```bash
    git clone https://github.com/ard-guilherme/looper-reports.git
    cd looper-reports
    ```

2.  **Crie e ative um ambiente virtual:**
    ```bash
    python -m venv venv
    source venv/bin/activate
    # No Windows, use: venv\Scripts\activate
    ```

3.  **Instale as dependências:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Crie o arquivo de ambiente (`.env`):**
    Crie um arquivo chamado `.env` na raiz do projeto e preencha com as seguintes variáveis:

    ```dotenv
    # Chave de API do Google Gemini
    GEMINI_API_KEY="sua_chave_de_api_aqui"

    # URI de conexão do MongoDB (usada pelo docker-compose)
    MONGO_URI="mongodb://mongodb:27017/"

    # Nome do banco de dados
    DB_NAME="gcoach_dev"

    # Caminho para o template do relatório
    REPORT_TEMPLATE_FILE="app/templates/report_template.html"
    ```

### 4.3. Executando a Aplicação

O `docker-compose` orquestra tanto o serviço da aplicação quanto o banco de dados MongoDB.

```bash
docker-compose up --build
```

A API estará disponível em `http://localhost:8000`. Você pode acessar a documentação interativa (Swagger UI) em `http://localhost:8000/docs`.

---

## 5. Como Usar

Para gerar um relatório, envie uma requisição `POST` para o endpoint `/api/v1/reports/generate/{student_id}`.

**Exemplo com `curl`:**

```bash
# Substitua o ID pelo ObjectId do aluno desejado
STUDENT_ID="68d9d29eec34f543218f9063"

curl -X POST http://localhost:8000/api/v1/reports/generate/$STUDENT_ID \
-H "Content-Type: application/json" \
-o relatorio_gerado.html

# Abra o relatório no seu navegador
# (No Linux)
xdg-open relatorio_gerado.html
# (No macOS)
open relatorio_gerado.html
```

O comando salvará o HTML do relatório gerado no arquivo `relatorio_gerado.html`.

---

## 6. Testes

O projeto utiliza `pytest` para testes de unidade e integração. Os testes validam o fluxo de orquestração do `ReportService`, mockando as chamadas ao banco de dados e ao LLM para garantir que a lógica de montagem do relatório está correta.

Para executar os testes:

```bash
# Certifique-se de que o ambiente virtual está ativado
source venv/bin/activate

# Execute o pytest
pytest
```
