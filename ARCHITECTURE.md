# Plano de Arquitetura e Especificações: Looper Reports AI

O sistema será construído como uma aplicação web backend que expõe uma API RESTful. O núcleo da aplicação será modular, separando claramente as responsabilidades de API, lógica de negócios (serviços), acesso a dados e a lógica dos agents de IA.

#### 1. Arquitetura Proposta

Adotaremos uma arquitetura em camadas (layered architecture) para promover a separação de conceitos:

*   **Camada de Apresentação (API):** Interface RESTful criada com **FastAPI**. Responsável por receber as requisições HTTP, validar os dados de entrada (usando Pydantic) e orquestrar as chamadas para a camada de serviço.
*   **Camada de Serviço (Lógica de Negócio):** Módulos Python que contêm a lógica principal. Ex: `ReportService` irá buscar dados do aluno, invocar o agent apropriado e formatar a saída.
*   **Camada de Agents (IA Core):** Componentes dedicados que encapsulam a lógica da **LangChain**. Cada agent terá um propósito específico (o primeiro será o `ReportGeneratorAgent`), com seu próprio prompt e cadeia de execução (chain).
*   **Camada de Acesso a Dados (Database):** Módulos responsáveis pela comunicação com o **MongoDB**. Usaremos a biblioteca **Motor**, o driver assíncrono oficial do MongoDB, para não bloquear a event loop do FastAPI durante as operações de I/O com o banco.

#### 2. Estrutura de Diretórios

Proponho a seguinte estrutura de arquivos para organizar o projeto de forma escalável:

```
looper-reports/
├── app/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── endpoints/
│   │   │   │   ├── __init__.py
│   │   │   │   └── reports.py      # Endpoint para gerar relatórios
│   │   │   └── router.py           # Agregador de rotas da v1
│   ├── agents/
│   │   ├── __init__.py
│   │   └── report_generator_agent.py # Lógica do agent com LangChain
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py           # Configurações (env vars)
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py           # Modelos Pydantic para o MongoDB
│   │   └── session.py          # Lógica de conexão com o MongoDB (Motor)
│   ├── services/
│   │   ├── __init__.py
│   │   └── report_service.py   # Lógica de negócio para relatórios
│   └── templates/
│       └── report_template.html # Template Jinja2 para o relatório HTML
├── .env                    # Variáveis de ambiente (NÃO versionar)
├── .gitignore
├── main.py                 # Ponto de entrada da aplicação FastAPI
└── requirements.txt        # Dependências do projeto
```

#### 3. Especificações dos Componentes

*   **`main.py`**:
    *   Inicializa a instância do FastAPI.
    *   Inclui o roteador principal da `app/api/v1/router.py`.
    *   Define um endpoint raiz (`/`) para health check.

*   **`requirements.txt`**:
    *   `fastapi`: O framework web.
    *   `uvicorn[standard]`: O servidor ASGI para rodar a aplicação.
    *   `motor`: Driver assíncrono para MongoDB.
    *   `pydantic`: Para validação de dados e configurações.
    *   `python-dotenv`: Para carregar variáveis do arquivo `.env`.
    *   `langchain`: Framework principal para os agents.
    *   `langchain-google-genai`: Integração específica para o Gemini.
    *   `jinja2`: Para renderizar o template HTML do relatório.

*   **`.env`**:
    *   `MONGO_CONNECTION_STRING`: String de conexão para seu cluster MongoDB.
    *   `GEMINI_API_KEY`: Sua chave de API para o Gemini.

*   **`app/core/config.py`**:
    *   Usará Pydantic `BaseSettings` para carregar e validar as variáveis de ambiente do `.env`.

*   **`app/db/models.py`**:
    *   Definirá modelos Pydantic que representam as coleções do MongoDB (ex: `StudentModel`), garantindo uma estrutura de dados consistente.

*   **`app/db/session.py`**:
    *   Criará e gerenciará o cliente de conexão assíncrona com o MongoDB usando `motor`.

*   **`app/agents/report_generator_agent.py`**:
    *   Conterá a função principal, ex: `generate(student_data: dict) -> str`.
    *   Inicializará o LLM do Gemini (`ChatGoogleGenerativeAI`).
    *   Definirá o `PromptTemplate` com as instruções para o agent e as variáveis de entrada (dados do aluno).
    *   Criará a `chain` (ex: `prompt | llm | StrOutputParser()`).
    *   Executará a `chain.ainvoke()` com os dados do aluno.

*   **`app/services/report_service.py`**:
    *   Terá uma função como `async def create_report_for_student(student_id: str)`.
    *   Usará a sessão do `motor` para buscar os dados do aluno no MongoDB.
    *   Processará e preparará os dados para o agent.
    *   Invocará o `report_generator_agent.generate()`.
    *   Receberá o texto gerado, combina-o com o template HTML e renderiza o relatório final.

*   **`app/api/v1/endpoints/reports.py`**:
    *   Definirá um endpoint `POST /reports/generate/{student_id}`.
    *   Receberá o `student_id` e chamará o `report_service`.
    *   Retornará uma `HTMLResponse` com o relatório finalizado.

#### 4. Fluxo de Geração de Relatório (End-to-End)

1.  Uma requisição `POST` é enviada para `/api/v1/reports/generate/some-student-id`.
2.  O endpoint em `reports.py` recebe a chamada e invoca o `ReportService`.
3.  O `ReportService` busca os dados completos do aluno `some-student-id` no MongoDB de forma assíncrona.
4.  O serviço formata esses dados e os passa para o `ReportGeneratorAgent`.
5.  O agent insere os dados no `PromptTemplate`, envia para a API do Gemini via LangChain e obtém a resposta em texto.
6.  O `ReportService` recebe o texto gerado, combina-o com o template HTML e renderiza o relatório final.
7.  O serviço retorna o HTML para o endpoint, que o envia como resposta à requisição inicial.
