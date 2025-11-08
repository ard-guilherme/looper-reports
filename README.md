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
2.  **API Endpoint:** O endpoint em `app/api/v1/endpoints/reports.py` recebe a chamada. Usando injeção de dependência, ele obtém uma sessão de banco de dados e chama o `ReportService`.
3.  **Busca de Dados (Service):** O `ReportService` (`app/services/report_service.py`) busca os dados do aluno no banco de dados `mario_bot_db`, consultando as coleções `students`, `checkins` e `macro_goals` de forma assíncrona.
4.  **Invocação do Agent (Service):** O serviço agrupa os dados coletados em um dicionário e os passa para o `ReportGeneratorAgent`.
5.  **Geração de Conteúdo (Agent):** O `ReportGeneratorAgent` (`app/agents/report_generator_agent.py`) insere os dados no `PromptTemplate` (carregado da variável de ambiente `REPORT_PROMPT`), envia a requisição para a API do Gemini via LangChain e obtém a resposta em formato Markdown.
6.  **Renderização de HTML (Service):** O `ReportService` converte o Markdown recebido para HTML e o renderiza dentro do template `report_template.html` usando Jinja2.
7.  **Resposta:** O endpoint da API retorna a `HTMLResponse` com o relatório finalizado para o cliente.

## 2. Guia de Uso e Instalação

### 2.1. Configuração do Ambiente

**Pré-requisitos:**
- Python 3.10+
- Git
- Uma instância do MongoDB acessível

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
    - Crie um arquivo `.env` na raiz do projeto.
    - Preencha as seguintes variáveis no arquivo `.env`:
      - `MONGO_CONNECTION_STRING`: A string de conexão completa para o seu banco de dados MongoDB.
      - `GEMINI_API_KEY`: Sua chave de API do Google Gemini.
      - `MONGO_DB_NAME`: O nome do banco de dados a ser utilizado (ex: `mario_bot_db`).
      - `REPORT_PROMPT`: O template do prompt que o agent de IA usará para gerar os relatórios.

### 2.2. Como Executar a Aplicação

Use o Uvicorn para iniciar o servidor FastAPI:

```bash
uvicorn main:app --reload
```

A API estará disponível em `http://127.0.0.1:8000`.

### 2.3. Como Usar

Para gerar um relatório, envie uma requisição `POST` para o seguinte endpoint:

`POST /api/v1/reports/generate/{student_id}`

Onde `{student_id}` é o ID do aluno no MongoDB.

A resposta será um HTML com o relatório gerado.