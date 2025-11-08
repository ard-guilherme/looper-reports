import json
from typing import Dict, Any
from bson import ObjectId
from datetime import datetime

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import settings

def json_serializer(obj):
    """Custom JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, ObjectId)):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

async def generate_report_content(student_data: Dict[str, Any]) -> str:
    """
    Generates a fitness report for a student using the Gemini model.

    Args:
        student_data: A dictionary containing the student's data, with keys like
                      'student_profile', 'checkins', and 'macro_goals'.

    Returns:
        The generated report content as a string.
    """
    # Initialize the language model
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", google_api_key=settings.GEMINI_API_KEY)

    # Create the prompt template from the environment variable
    prompt = PromptTemplate(
        template=settings.REPORT_PROMPT,
        input_variables=["student_profile", "checkins", "macro_goals", "bioimpedance_data", "past_reports"],
    )

    # Define the generation chain
    chain = prompt | llm | StrOutputParser()

    # Format each part of the student data for the prompt
    formatted_inputs = {
        key: json.dumps(value, indent=2, ensure_ascii=False, default=json_serializer)
        for key, value in student_data.items()
    }

    # Invoke the chain asynchronously
    report = await chain.ainvoke(formatted_inputs)

    return report
