# Looper Reports: Motor de Geração de Relatórios de Performance com IA

---

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python) ![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-green?style=for-the-badge&logo=fastapi) ![Docker](https://img.shields.io/badge/Docker-20.10%2B-blue?style=for-the-badge&logo=docker) ![MongoDB](https://img.shields.io/badge/MongoDB-4.4%2B-green?style=for-the-badge&logo=mongodb) ![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-blue?style=for-the-badge&logo=openai)

## 1. Sobre o Projeto

O **Looper Reports** é um sistema de back-end projetado para automatizar a criação de relatórios de progresso semanais para alunos de coaching de alta performance. O sistema consome dados brutos de diversas fontes (nutrição, sono, treinos) e os transforma em um relatório HTML detalhado, estilizado e repleto de insights, utilizando um motor de IA para análise e geração de texto.

O objetivo principal é liberar o coach do trabalho manual de compilação e análise de dados, permitindo que ele se concentre na estratégia e no relacionamento com o aluno, ao mesmo tempo que entrega um produto de altíssima qualidade e valor percebido.

### 1.1. Funcionalidades Principais

- **Geração de Relatório via API:** Um único endpoint que orquestra todo o processo.
- **Análise de Múltiplas Fontes:** Agrega dados de check-ins diários, metas de longo prazo e relatórios anteriores.
- **Motor de IA Modular:** Utiliza um padrão de Agente/Orquestrador para gerar cada seção do relatório de forma independente e especializada.
- **Geração Baseada em Prompts:** A lógica de geração de cada seção é definida em arquivos de prompt de texto, permitindo fácil iteração e ajuste fino sem alterar o código.
- **Template HTML:** O relatório final é montado a partir de um template HTML, garantindo consistência visual e separação entre conteúdo e apresentação.

---

## 2. Arquitetura e Fluxo de Dados

O sistema foi desenhado com foco em modularidade e manutenibilidade, utilizando um padrão de **Orquestrador-Agente**.

### 2.1. Componentes

1.  **API (FastAPI):**
    -   Expõe o endpoint principal (`/reports/{student_id}`) que dispara a geração do relatório.
    -   Responsável pela validação da requisição e por injetar as dependências necessárias (como a conexão com o banco de dados).

2.  **Orquestrador (`ReportService`:
    -   É o cérebro do sistema. Ao ser chamado pela API, ele executa as seguintes etapas:
        1.  **Coleta de Dados:** Busca no MongoDB todos os dados relevantes para a semana do aluno (check-ins, metas, relatórios passados).
        2.  **Construção de Contexto:** Processa e analisa os dados brutos, criando um "super-prompt" ou contexto base que será o alicerce para todas as chamadas de IA.
        3.  **Coordenação de Agentes:** Invoca o `ReportGeneratorAgent` sequencialmente para cada seção do relatório (visão geral, nutrição, sono, etc.).
        4.  **Montagem do HTML:** Pega o conteúdo gerado por cada agente e o insere no template HTML principal.
        5.  **Persistência:** Salva o relatório HTML final no banco de dados.

3.  **Agente (`ReportGeneratorAgent`:
    -   Um agente especializado que atua como uma interface com o LLM (OpenAI GPT-4).
    -   Recebe o **tipo de seção** a ser gerada e o **contexto base** do orquestrador.
    -   Carrega o **prompt específico** para a seção solicitada a partir do diretório `app/agents/prompts/sections/`.
    -   Formata o prompt final com os dados de contexto e o envia para o LLM.
    -   Retorna o texto (HTML) gerado pelo LLM para o orquestrador.

### 2.2. Fluxo de Dados

```
Requisição HTTP (POST /reports/{student_id})
        |
        v
+--------------------+
| API (FastAPI)      |
+--------------------+ 
        |
        v
+-----------------------------+
| Orquestrador (ReportService) |
+-----------------------------+
        |         ^         
        |         | (HTML de cada seção)
        v         |
+----------------+  +-----------------------------+
| MongoDB        |  | Agente (ReportGeneratorAgent) |
| (Coleta de Dados)|
+----------------+          |         ^ (Texto gerado)
                          |
                          v         |
                  +---------------------+
                  | LLM (OpenAI GPT-4)  |
                  +---------------------+
```

---

## 3. Tecnologias Utilizadas

- **Back-end:** Python 3.12
- **Framework API:** FastAPI
- **Banco de Dados:** MongoDB (com `motor` para operações assíncronas)
- **IA & LLM:** OpenAI GPT-4
- **Containerização:** Docker & Docker Compose
- **Análise de Dados:** `numpy`
- **Testes:** `pytest` e `pytest-asyncio`

---

## 4. Guia de Instalação e Execução

### 4.1. Pré-requisitos

- Docker e Docker Compose instalados.
- Python 3.10+ e `pip` para gerenciamento de pacotes.
- Acesso a uma chave de API da OpenAI.

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
    ```

3.  **Instale as dependências:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Crie o arquivo de ambiente (`.env`):**
    Crie um arquivo chamado `.env` na raiz do projeto e preencha com as seguintes variáveis:

    ```dotenv
    # Chave de API da OpenAI
    OPENAI_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

    # URI de conexão do MongoDB
    MONGO_URI="mongodb://localhost:27017/"

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

A API estará disponível em `http://localhost:8000/docs` para interação.

---

## 5. Como Usar

Para gerar um relatório, envie uma requisição `POST` para o endpoint `/api/v1/reports/{student_id}`.

**Exemplo com `curl`:**

```bash
curl -X POST http://localhost:8000/api/v1/reports/60d5ec49c3a3a4e6c8b45678 \
-H "Content-Type: application/json" \
-o relatorio_gerado.html
```

Onde `60d5ec49c3a3a4e6c8b45678` é o `ObjectId` do aluno no banco de dados. O comando salvará o HTML do relatório gerado no arquivo `relatorio_gerado.html`.

---

## 6. Testes

O projeto utiliza `pytest` para garantir a qualidade e a estabilidade do código. Os testes estão focados em validar o fluxo de orquestração do `ReportService`, mockando as chamadas ao banco de dados e ao LLM para garantir que a lógica de montagem do relatório está correta.

Para executar os testes:

```bash
# Certifique-se de que o ambiente virtual está ativado
source venv/bin/activate

# Execute o pytest
pytest
```