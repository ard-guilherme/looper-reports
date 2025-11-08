import logging
from bson import ObjectId
from datetime import datetime, UTC
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agents.report_generator_agent import generate_report_content

logger = logging.getLogger(__name__)

async def create_report_for_student(student_id: str, db: AsyncIOMotorDatabase) -> str:
    """
    Orchestrates the report generation for a specific student and returns HTML.
    """
    logger.info(f"Starting report creation for student_id: {student_id}")
    if not ObjectId.is_valid(student_id):
        logger.warning(f"Invalid ObjectId format for student_id: {student_id}")
        raise HTTPException(status_code=400, detail=f"Invalid student ID: {student_id}")

    student_obj_id = ObjectId(student_id)

    # --- 1. Fetch all data sources ---
    logger.debug(f"Fetching data for student_id: {student_id}")
    student_data = await db["students"].find_one({"_id": student_obj_id})
    if not student_data:
        logger.error(f"Student not found for student_id: {student_id}")
        raise HTTPException(status_code=404, detail=f"Student with ID {student_id} not found")

    checkins_data = await db["checkins"].find({"student_id": student_obj_id}).to_list(length=None)
    macro_goals_data = await db["macro_goals"].find({"student_id": student_obj_id}).to_list(length=None)
    bioimpedance_data = await db["bioimpedancias"].find({"student_id": student_obj_id}).to_list(length=None)
    past_reports_data = await db["relatorios"].find({"student_id": student_obj_id}).sort("generated_at", -1).limit(2).to_list(length=2)
    logger.info(f"Data fetched for student_id: {student_id}. Found {len(checkins_data)} check-ins, {len(macro_goals_data)} macro goals, {len(bioimpedance_data)} bioimpedance records, {len(past_reports_data)} past reports.")

    # --- 2. Format data for the prompt ---
    # This is a simplified example. In a real scenario, you'd format this much more carefully
    # to match the exact structure expected by the prompt_template.txt
    formatted_data_for_prompt = f"""
ALUNO: {student_data.get('name', 'N/A')}
SEMANA: [Número] de [Mês] 2025 ([DD/MM] - [DD/MM])

TREINOS:
{checkins_data}

NUTRIÇÃO DIÁRIA:
{macro_goals_data}

SONO DIÁRIO:
{bioimpedance_data}

DADOS SEMANA ANTERIOR (para comparação):
[Dados da semana anterior aqui]

CONTEXTO ADICIONAL:
[Informações relevantes: rotina de trabalho, limitações, eventos especiais, etc.]
"""
    logger.debug(f"Formatted data for prompt for student_id: {student_id}")

    # --- 3. Generate the new report content (HTML) ---
    logger.info(f"Invoking report generation agent for student_id: {student_id}")
    final_html_output = await generate_report_content(formatted_data_for_prompt)
    logger.info(f"Agent successfully generated HTML content for student_id: {student_id}")

    # --- 4. Save the newly generated report to the database ---
    new_report = {
        "student_id": student_obj_id,
        "generated_at": datetime.now(UTC),
        "html_content": final_html_output
    }
    logger.info(f"Saving new report to database for student_id: {student_id}")
    await db["relatorios"].insert_one(new_report)
    logger.info(f"Successfully saved new report for student_id: {student_id}")

    # --- 5. Return the final report ---
    return final_html_output

