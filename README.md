# Looper Reports AI

Este projeto é um hub de automação para o sistema de coaching fitness Looper, focado na geração de relatórios de progresso para alunos usando IA com Gemini e LangChain.

## 1. Documentação Técnica

### 1.1. Core Technologies

- **Backend Framework:** FastAPI
- **Servidor ASGI:** Uvicorn
- **Banco de Dados:** MongoDB (com driver assíncrono Motor)
- **IA & Orquestração:** LangChain
- **Modelo de Linguagem:** Google Gemini Pro
- **Validação de Dados:** Pydantic
- **Templates:** Jinja2
- **Conversão de Markdown:** Markdown

### 1.2. Arquitetura

Adotamos uma arquitetura em camadas (layered architecture) para promover a separação de conceitos e garantir a escalabilidade do projeto.

- **Camada de Apresentação (API):** Interface RESTful criada com **FastAPI**. Responsável por receber as requisições HTTP, validar os dados de entrada e orquestrar as chamadas para a camada de serviço. Fica em `app/api/`.

- **Camada de Serviço (Lógica de Negócio):** Módulos Python que contêm a lógica principal. O `ReportService` (`app/services/report_service.py`) é responsável por buscar os dados do aluno, invocar o agent de IA e renderizar o template HTML final.

- **Camada de Agents (IA Core):** Componentes dedicados que encapsulam a lógica da **LangChain**. O `ReportGeneratorAgent` (`app/agents/report_generator_agent.py`) possui o prompt, o modelo de linguagem (LLM) e a cadeia de execução para gerar o conteúdo do relatório.

- **Camada de Acesso a Dados (Database):** Módulos responsáveis pela comunicação com o **MongoDB**. Usamos a biblioteca **Motor**, o driver assíncrono oficial, para não bloquear a event loop do FastAPI. A lógica de conexão e os modelos de dados Pydantic ficam em `app/db/`.

### 1.3. Estrutura de Diretórios

```
looper-reports/
├── app/                  # Código fonte da aplicação
│   ├── api/              # Módulos da API (endpoints, roteadores)
│   ├── agents/           # Lógica dos agents de IA com LangChain
│   ├── core/             # Configurações globais da aplicação
│   ├── db/               # Conexão com o banco e modelos de dados
│   ├── services/         # Lógica de negócio
│   └── templates/        # Templates HTML (Jinja2)
├── .env                  # Arquivo para variáveis de ambiente (não versionado)
├── main.py               # Ponto de entrada da aplicação FastAPI
└── requirements.txt      # Dependências do projeto
```

### 1.4. Fluxo de Geração de Relatório (End-to-End)

1.  **Requisição:** Um cliente envia uma requisição `POST` para o endpoint `/api/v1/reports/generate/{student_id}`.
2.  **API Endpoint:** O endpoint em `app/api/v1/endpoints/reports.py` recebe a chamada e, usando injeção de dependência, invoca o `ReportService`.
3.  **Busca de Dados (Service):** O `ReportService` (`app/services/report_service.py`) busca os dados do aluno no banco de dados `mario_bot_db`:
    - Busca o perfil do aluno na coleção `students`.
    - Busca os **check-ins dos últimos 7 dias** na coleção `checkins`. Estes documentos são a fonte principal para dados diários de treino, sono e nutrição.
    - Busca os 2 últimos relatórios na coleção `relatorios` para extrair dados comparativos da semana anterior.
4.  **Formatação do Prompt (Service):** Esta é uma etapa crucial. O serviço processa os dados brutos para montar uma única string de texto que servirá de contexto para o LLM:
    - **Dados de Treino:** A função `_parse_training_journal` lê a string `training_journal` de cada check-in, extrai os exercícios e séries, e os formata.
    - **Dados de Nutrição e Sono:** Funções auxiliares extraem os dados de `nutrition` e `sleep` de cada check-in e os formatam.
    - **Dados da Semana Anterior:** A função `_format_previous_week_data` usa a biblioteca **BeautifulSoup** para parsear o conteúdo HTML do relatório mais recente e extrair as métricas de comparação (calorias, volume de treino, etc.).
    - Todos os dados formatados são inseridos em uma estrutura de texto definida pelo `prompt_template.txt`.
5.  **Invocação do Agent (Service):** O serviço passa a string do prompt, agora rica em contexto, para o `ReportGeneratorAgent`.
6.  **Geração de Conteúdo (Agent):** O `ReportGeneratorAgent` (`app/agents/report_generator_agent.py`) insere a string no `PromptTemplate` (carregado de `app/agents/prompts/report_prompt.txt`), envia a requisição para a API do Gemini e instrui o modelo a gerar o **HTML completo e final** do relatório, já com todos os placeholders preenchidos.
7.  **Salvamento do Relatório (Service):** O serviço cria um novo documento com o ID do aluno, a data de geração e o conteúdo HTML final recebido do agent, e o **salva na coleção `relatorios`**.
8.  **Resposta:** O endpoint da API retorna a `HTMLResponse` com o relatório recém-gerado para o cliente.

## 2. Guia de Uso e Instalação

### 2.1. Executando com Docker (Recomendado)

**Pré-requisitos:**
- Docker e Docker Compose

1.  **Configure as variáveis de ambiente:**
    - Crie um arquivo `.env` na raiz do projeto.
    - Preencha as variáveis, especialmente `GEMINI_API_KEY` e `MONGO_CONNECTION_STRING` (que deve apontar para o seu MongoDB Atlas).

2.  **Execute o script de deploy:**
    ```bash
    ./deploy.sh
    ```
    Isso irá construir a imagem da API e iniciar o container em background.

3.  **Para parar o container:**
    ```bash
    docker-compose down
    ```

### 2.2. Executando Localmente (Sem Docker)

**Pré-requisitos:**
- Python 3.10+
- Git
- Uma instância do MongoDB acessível (local ou Atlas)

1.  **Clone o repositório:**
    ```bash
    git clone https://github.com/ard-guilherme/looper-reports.git
    cd looper-reports
    ```

2.  **Crie e ative um ambiente virtual:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    # No Windows, use: venv\Scripts\activate
    ```

3.  **Instale as dependências:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure as variáveis de ambiente:**
    - Crie um arquivo `.env` e preencha as variáveis. A `MONGO_CONNECTION_STRING` deve apontar para o seu MongoDB (ex: `mongodb://localhost:27017/looper_db` ou sua string do Atlas).

### 2.3. Como Usar

Para gerar um relatório, envie uma requisição `POST` para o seguinte endpoint:

`POST /api/v1/reports/generate/{student_id}`

Onde `{student_id}` é o ID do aluno no MongoDB.

A resposta será um HTML com o relatório gerado.