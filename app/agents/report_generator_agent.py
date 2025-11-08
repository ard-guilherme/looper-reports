import json
from typing import Dict, Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import settings

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
    llm = ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=settings.GEMINI_API_KEY)

    # Create the prompt template from the environment variable
    prompt = PromptTemplate(
        template=settings.REPORT_PROMPT,
        input_variables=["student_profile", "checkins", "macro_goals"],
    )

    # Define the generation chain
    chain = prompt | llm | StrOutputParser()

    # Format each part of the student data for the prompt
    formatted_inputs = {
        "student_profile": json.dumps(student_data.get("student_profile", {}), indent=2, ensure_ascii=False),
        "checkins": json.dumps(student_data.get("checkins", []), indent=2, ensure_ascii=False),
        "macro_goals": json.dumps(student_data.get("macro_goals", []), indent=2, ensure_ascii=False),
    }

    # Invoke the chain asynchronously
    report = await chain.ainvoke(formatted_inputs)

    return report
