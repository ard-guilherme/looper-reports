import logging
import re
from bson import ObjectId
from datetime import datetime, UTC, timedelta
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from bs4 import BeautifulSoup

from app.agents.report_generator_agent import generate_report_content

logger = logging.getLogger(__name__)

def _parse_training_journal(journal: str) -> str:
    """Parses the raw training journal string into a structured format for the prompt."""
    if not journal:
        return "Diário de treino não fornecido.\n"

    # Split by double newline, which typically separates exercises in the Hevy app format
    exercise_blocks = journal.strip().split('\n\n')
    
    # The first block is often a title, and the last is the Hevy signature. We skip them.
    # A more robust way is to filter out blocks that don't contain "Série".
    exercise_blocks = [b for b in exercise_blocks if "Série" in b]

    # Format for the prompt
    prompt_output = []
    for block in exercise_blocks:
        lines = block.split('\n')
        exercise_name = lines[0]
        sets = [f"    • {s.strip()}" for s in lines[1:]]
        exercise_str = f"{exercise_name}\n" + "\n".join(sets)
        prompt_output.append(exercise_str)

    return "\n\n".join(prompt_output)

def _format_training_data(checkins: list) -> str:
    """Formats check-in data into a training data string for the prompt."""
    if not checkins:
        return "Nenhum treino registrado na semana.\n"
    
    formatted_lines = []
    for checkin in checkins:
        date = datetime.fromisoformat(checkin.get("checkin_date")).strftime("%d/%m/%Y")
        journal = checkin.get("training", {}).get("training_journal", "")
        
        if journal:
            parsed_journal = _parse_training_journal(journal)
            formatted_lines.append(f"{date} - Treino\n{parsed_journal}")
        
    return "\n\n".join(formatted_lines)

def _format_nutrition_data(checkins: list) -> str:
    """Formats nutrition data from check-ins into a string for the prompt."""
    if not checkins:
        return "Nenhum dado de nutrição registrado na semana.\n"
    
    formatted_lines = []
    for checkin in checkins:
        date = datetime.fromisoformat(checkin.get("checkin_date")).strftime("%d/%m/%Y")
        nutrition = checkin.get("nutrition", {})
        line = f"{date}: {nutrition.get('calories', 0)}kcal | {nutrition.get('protein', 0)}g | {nutrition.get('carbs', 0)}g | {nutrition.get('fat', 0)}g"
        formatted_lines.append(line)
        
    return "\n".join(formatted_lines)

def _format_sleep_data(checkins: list) -> str:
    """Formats sleep data from check-ins into a string for the prompt."""
    if not checkins:
        return "Nenhum dado de sono registrado na semana.\n"
    
    formatted_lines = []
    for checkin in checkins:
        date = datetime.fromisoformat(checkin.get("checkin_date")).strftime("%d/%m/%Y")
        sleep = checkin.get("sleep", {})
        duration = sleep.get("sleep_duration_hours", 0)
        quality = sleep.get("sleep_quality_rating", 0)
        start_time = sleep.get("sleep_start_time", "--:--")
        end_time = sleep.get("sleep_end_time", "--:--")
        line = f"{date}: {duration:.1f}h | Qualidade {quality}/5 | {start_time}-{end_time}"
        formatted_lines.append(line)
        
    return "\n".join(formatted_lines)

def _format_previous_week_data(past_reports: list) -> str:
    """Formats past report data by parsing its HTML content."""
    if not past_reports:
        return "Nenhum relatório anterior encontrado para comparação.\n"
    
    try:
        latest_report_html = past_reports[0].get("html_content", "")
        soup = BeautifulSoup(latest_report_html, 'html.parser')
        
        metrics = soup.find_all('div', class_='metric-item')
        
        data = {
            "Calorias médias": "N/A",
            "Proteína média": "N/A",
            "Volume total": "N/A",
            "Sono médio": "N/A" # This metric is not in the template, needs to be added
        }

        for metric in metrics:
            label = metric.find('div', class_='metric-label').text.strip().lower()
            value = metric.find('div', class_='metric-value').text.strip()
            if 'calorias médias' in label:
                data["Calorias médias"] = value
            elif 'proteína média' in label:
                data["Proteína média"] = value
            elif 'volume total' in label:
                data["Volume total"] = value

        return f"""Calorias médias: {data['Calorias médias']}
Proteína média: {data['Proteína média']}
Volume treino: {data['Volume total']}
Sono médio: {data['Sono médio']}
"""
    except Exception as e:
        logger.error(f"Error parsing previous report HTML: {e}")
        return "Erro ao processar dados da semana anterior.\n"

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

    # Fetch data for the last 7 days
    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=7)

    checkins_data = await db["checkins"].find({
        "student_id": student_obj_id, 
        "checkin_date": {
            "$gte": start_date.strftime("%Y-%m-%d"), 
            "$lte": end_date.strftime("%Y-%m-%d")
        }
    }).to_list(length=None)
    
    past_reports_data = await db["relatorios"].find({"student_id": student_obj_id}).sort("generated_at", -1).limit(2).to_list(length=2)
    logger.info(f"Data fetched for student_id: {student_id}. Found {len(checkins_data)} check-ins and {len(past_reports_data)} past reports.")

    # --- 2. Format data for the prompt ---
    formatted_trainings = _format_training_data(checkins_data)
    formatted_nutrition = _format_nutrition_data(checkins_data)
    formatted_sleep = _format_sleep_data(checkins_data)
    formatted_previous_week = _format_previous_week_data(past_reports_data)
    
    # Dynamic date placeholders
    week_number = end_date.isocalendar()[1]
    month_name = end_date.strftime("%B")
    week_start_str = start_date.strftime("%d/%m")
    week_end_str = end_date.strftime("%d/%m")
    week_str = f"Semana {week_number} de {month_name} 2025 ({week_start_str} - {week_end_str})"

    formatted_data_for_prompt = f"""
ALUNO: {student_data.get('name', 'N/A')}
SEMANA: {week_str}

TREINOS:
{formatted_trainings}

NUTRIÇÃO DIÁRIA:
{formatted_nutrition}

SONO DIÁRIO:
{formatted_sleep}

DADOS SEMANA ANTERIOR (para comparação):
{formatted_previous_week}

CONTEXTO ADICIONAL:
{student_data.get('additional_context', 'Nenhum contexto adicional fornecido.')}
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

