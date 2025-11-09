import logging
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import settings

logger = logging.getLogger(__name__)

PROMPT_FILES = {
    "overview": "sections/overview_prompt.txt",
    "nutrition_analysis": "sections/nutrition_analysis_prompt.txt",
    "sleep_analysis": "sections/sleep_analysis_prompt.txt",
}

async def generate_report_section(section_type: str, context_data: str, temperature: float = 0.7) -> str:
    """
    Gera o conteúdo para uma seção específica do relatório usando um LLM.

    Args:
        section_type: O tipo de seção a ser gerada (ex: 'overview').
        context_data: Os dados pré-formatados e analisados para o prompt.
        temperature: A temperatura do modelo para controlar a criatividade.

    Returns:
        O conteúdo de texto gerado para a seção.
    """
    if section_type not in PROMPT_FILES:
        logger.error(f"Tipo de seção inválido: {section_type}")
        raise ValueError(f"Nenhum arquivo de prompt definido para a seção '{section_type}'")

    prompt_filename = PROMPT_FILES[section_type]
    prompt_filepath = f"{settings.PROMPTS_DIR}/{prompt_filename}"
    logger.info(f"Gerando seção '{section_type}' usando o prompt '{prompt_filepath}'")

    try:
        with open(prompt_filepath, "r", encoding="utf-8") as f:
            template_content = f.read()
    except FileNotFoundError:
        logger.error(f"Arquivo de prompt não encontrado: {prompt_filepath}")
        raise

    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-pro",
        google_api_key=settings.GEMINI_API_KEY,
        temperature=temperature,
        max_output_tokens=8192
    )

    prompt = PromptTemplate(
        template=template_content,
        input_variables=["context_data"],
    )

    chain = prompt | llm | StrOutputParser()

    logger.debug(f"Invocando LLM para a seção '{section_type}'.")
    section_content = await chain.ainvoke({"context_data": context_data})
    logger.info(f"Conteúdo para a seção '{section_type}' gerado com sucesso.")

    return section_content.strip()