# Looper Reports AI

Este projeto é um hub de automação para o sistema de coaching fitness Looper, focado na geração de relatórios de progresso para alunos usando IA com Gemini e LangChain.

## Arquitetura

Para detalhes sobre a arquitetura do projeto, consulte o arquivo [ARCHITECTURE.md](ARCHITECTURE.md).

## Configuração do Ambiente

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
    ```

3.  **Instale as dependências:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure as variáveis de ambiente:**
    - Renomeie ou copie o arquivo `.env.example` para `.env`.
    - Preencha as seguintes variáveis no arquivo `.env`:
      - `MONGO_CONNECTION_STRING`: A string de conexão completa para o seu banco de dados MongoDB.
      - `GEMINI_API_KEY`: Sua chave de API do Google Gemini.
      - `MONGO_DB_NAME`: O nome do banco de dados a ser utilizado (ex: `mario_bot_db`).
      - `REPORT_PROMPT`: O template do prompt que o agent de IA usará para gerar os relatórios.

## Como Executar a Aplicação

Use o Uvicorn para iniciar o servidor FastAPI:

```bash
uvicorn main:app --reload
```

A API estará disponível em `http://127.0.0.1:8000`.

## Como Usar

Para gerar um relatório, envie uma requisição `POST` para o seguinte endpoint:

`POST /api/v1/reports/generate/{student_id}`

Onde `{student_id}` é o ID do aluno no MongoDB.

A resposta será um HTML com o relatório gerado.
