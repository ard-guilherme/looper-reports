import logging
import os
import re
from app.core.config import settings
from langchain_google_genai.chat_models import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

logger = logging.getLogger(__name__)

# Mapeia os tipos de seção para seus respectivos arquivos de prompt
PROMPT_FILES = {
    "overview": "sections/overview_prompt.txt",
    "nutrition_analysis": "sections/nutrition_analysis_prompt.txt",
    "sleep_analysis": "sections/sleep_analysis_prompt.txt",
    "training_analysis": "sections/training_analysis_prompt.txt",
    "detailed_insights": "sections/detailed_insights_prompt.txt",
    "recommendations": "sections/recommendations_prompt.txt",
    "conclusion": "sections/conclusion_prompt.txt",
}

def _load_prompt_template(section_type: str) -> str:
    """Carrega o template de prompt do arquivo correspondente."""
    prompt_file = PROMPT_FILES.get(section_type)
    if not prompt_file:
        raise ValueError(f"Tipo de seção inválido: {section_type}")

    base_dir = os.path.dirname(__file__)
    file_path = os.path.join(base_dir, "prompts", prompt_file)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Arquivo de prompt não encontrado: {file_path}")
        raise

def _sanitize_html_output(raw_output: str) -> str:
    """Limpa a saída do LLM, removendo texto conversacional, blocos de código markdown e padrões repetitivos."""
    sanitized_output = re.sub(r'^```html\n', '', raw_output, flags=re.MULTILINE)
    sanitized_output = re.sub(r'\n```$', '', sanitized_output, flags=re.MULTILINE)

    common_intros = [
        r"Com certeza, GN Coach. Segue a análise.*?:\n+",
        r"Com certeza. Como assistente do GN Coach,.*?:\n+",
        r"Com base nos dados fornecidos, aqui está a análise.*?:\n+",
        r"Análise Rápida:.*?---\n+",
        r"BLOCO HTML DE.*?:\n+",
    ]
    for intro in common_intros:
        sanitized_output = re.sub(intro, '', sanitized_output, flags=re.IGNORECASE | re.DOTALL)

    # Remove repeated single characters (like 't t t t t t t') at the beginning of the output
    sanitized_output = re.sub(r'^(?:(\S)\s)\1(?:\s\1){2,}\s*\n*', '', sanitized_output, flags=re.MULTILINE)

    return sanitized_output.strip()

async def generate_report_section(section_type: str, context_data: str, student_name: str) -> str:
    """
    Gera uma seção específica do relatório usando o LLM (Google Gemini via LangChain).

    Args:
        section_type: O tipo de seção a ser gerada (ex: 'overview').
        context_data: A string de contexto com todos os dados do aluno.
        student_name: O nome do aluno para garantir que não haja vazamento de dados.

    Returns:
        O conteúdo HTML gerado e sanitizado para a seção.
    """
    logger.info(f"Gerando seção do relatório com LangChain e Gemini: {section_type} para o aluno {student_name}")
    try:
        prompt_template_str = _load_prompt_template(section_type)
        
        # Configura o modelo Gemini
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-pro",
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.7,
            convert_system_message_to_human=True # Necessário para Gemini
        )

        # Cria o prompt a partir do template
        prompt = ChatPromptTemplate.from_template(prompt_template_str)

        # Define a cadeia de execução (prompt -> modelo -> parser de saída)
        chain = prompt | llm | StrOutputParser()

        # Log do contexto completo para depuração
        logger.debug(f"Contexto completo para a seção '{section_type}':\n{context_data}")

        # Invoca a cadeia com os dados de contexto
        raw_content = await chain.ainvoke({"context_data": context_data, "student_name": student_name})

        # Sanitiza a saída para garantir que é apenas HTML
        sanitized_content = _sanitize_html_output(raw_content)
        
        logger.info(f"Seção '{section_type}' gerada com sucesso para {student_name}.")
        return sanitized_content

    except Exception as e:
        logger.error(f"Erro ao gerar a seção '{section_type}' com LangChain: {e}")
        return f"<p>Erro ao gerar a seção <strong>{section_type}</strong>.</p>"