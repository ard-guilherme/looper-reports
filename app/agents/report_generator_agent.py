import json
import logging
from typing import Dict, Any
from bson import ObjectId
from datetime import datetime

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import settings

logger = logging.getLogger(__name__)

def json_serializer(obj):
    """Custom JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, ObjectId)):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

async def generate_report_content(user_data_for_prompt: str) -> str:
    """
    Generates a fitness report for a student using the Gemini model.

    Args:
        user_data_for_prompt: A pre-formatted string containing all student data for the prompt.

    Returns:
        The generated report content as an HTML string.
    """
    logger.info("Initializing LLM and prompt template.")
    # Initialize the language model
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", google_api_key=settings.GEMINI_API_KEY)

    # Read prompt template from file
    try:
        with open(settings.REPORT_PROMPT_FILE, "r", encoding="utf-8") as f:
            prompt_template_content = f.read()
    except FileNotFoundError:
        logger.error(f"Prompt file not found: {settings.REPORT_PROMPT_FILE}")
        raise

    # Create the prompt template
    prompt = PromptTemplate(
        template=prompt_template_content + "\n\n" + "DADOS DO ALUNO:\n{user_data_for_prompt}",
        input_variables=["user_data_for_prompt"],
    )

    # Define the generation chain
    chain = prompt | llm | StrOutputParser()

    logger.debug("Invoking LLM chain with formatted inputs.")

    # Invoke the chain asynchronously
    report = await chain.ainvoke({"user_data_for_prompt": user_data_for_prompt})
    logger.info("LLM chain invocation complete.")

    return report
