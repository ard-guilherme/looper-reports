import logging
import re
from bson import ObjectId
from datetime import datetime, UTC, timedelta
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from bs4 import BeautifulSoup
import numpy as np

from app.agents.report_generator_agent import generate_report_content

logger = logging.getLogger(__name__)


def _analyze_and_format_data(checkins: list, student: dict, past_reports: list, macro_goals: dict) -> str:
    """Analyzes all weekly data and formats it into a single string for the LLM prompt."""
    # --- 1. Nutrition Analysis ---
    daily_nutrition = [c.get('nutrition', {}) for c in checkins]
    calories = [n.get('calories', 0) for n in daily_nutrition if n.get('calories', 0) > 0]
    proteins = [n.get('protein', 0) for n in daily_nutrition if n.get('protein', 0) > 0]
    
    avg_calories = np.mean(calories) if calories else 0
    avg_proteins = np.mean(proteins) if proteins else 0
    calorie_cv = (np.std(calories) / avg_calories) * 100 if avg_calories > 0 else 0
    
    protein_goal = macro_goals.get('protein', 0)
    protein_adherence = (avg_proteins / protein_goal) * 100 if protein_goal > 0 else 0
    
    # --- 2. Sleep Analysis ---
    daily_sleep = [c.get('sleep', {}) for c in checkins]
    sleep_hours = [s.get('sleep_duration_hours', 0) for s in daily_sleep if s.get('sleep_duration_hours', 0) > 0]
    avg_sleep_hours = np.mean(sleep_hours) if sleep_hours else 0

    # --- 3. Training Analysis ---
    training_journals = [c.get('training', {}).get('training_journal', '') for c in checkins]
    total_sets = sum(journal.lower().count('série') for journal in training_journals)

    # --- 4. Previous Week Data ---
    previous_week_data = _parse_previous_week_data(past_reports)

    # --- 5. Format for Prompt ---
    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=7)
    week_number = end_date.isocalendar()[1]
    month_name = end_date.strftime("%B")
    week_str = f"Semana {week_number} de {month_name} 2025 ({start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m')})"

    prompt = f"""
ALUNO: {student.get('name', 'N/A')}
SEMANA: {week_str}

# DADOS BRUTOS DA SEMANA

TREINOS:
{_format_training_data(checkins)}

NUTRIÇÃO DIÁRIA:
{_format_nutrition_data(checkins)}

SONO DIÁRIO:
{_format_sleep_data(checkins)}

# DADOS ANALÍTICOS

## RESUMO NUTRICIONAL
- Calorias Médias: {avg_calories:.0f} kcal
- Proteína Média: {avg_proteins:.0f}g (Meta: {protein_goal}g, Aderência: {protein_adherence:.0f}%)
- Coeficiente de Variação (Calorias): {calorie_cv:.1f}%

## RESUMO SONO
- Média de Sono: {avg_sleep_hours:.1f} horas/noite

## RESUMO TREINO
- Volume Total (Séries): {total_sets} séries

## DADOS SEMANA ANTERIOR (para comparação):
{previous_week_data}

CONTEXTO ADICIONAL:
{student.get('additional_context', 'Nenhum contexto adicional fornecido.')}
"""
    return prompt

def _parse_training_journal(journal: str) -> str:
    """Parses the raw training journal string into a structured format for the prompt."""
    if not journal: return "Diário de treino não fornecido.\n"
    exercise_blocks = journal.strip().split('\n\n')
    exercise_blocks = [b for b in exercise_blocks if "Série" in b]
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
    if not checkins: return "Nenhum treino registrado na semana.\n"
    lines = []
    for checkin in checkins:
        date = datetime.fromisoformat(checkin.get("checkin_date")).strftime("%d/%m/%Y")
        journal = checkin.get("training", {}).get("training_journal", "")
        if journal: lines.append(f"**{date}**\n{_parse_training_journal(journal)}")
    return "\n\n".join(lines)

def _format_nutrition_data(checkins: list) -> str:
    """Formats nutrition data from check-ins into a string for the prompt."""
    if not checkins: return "Nenhum dado de nutrição registrado na semana.\n"
    lines = []
    for checkin in checkins:
        date = datetime.fromisoformat(checkin.get("checkin_date")).strftime("%d/%m/%Y")
        n = checkin.get("nutrition", {})
        lines.append(f"{date}: {n.get('calories', 0)}kcal | {n.get('protein', 0)}g | {n.get('carbs', 0)}g | {n.get('fat', 0)}g")
    return "\n".join(lines)

def _format_sleep_data(checkins: list) -> str:
    """Formats sleep data from check-ins into a string for the prompt."""
    if not checkins: return "Nenhum dado de sono registrado na semana.\n"
    lines = []
    for checkin in checkins:
        date = datetime.fromisoformat(checkin.get("checkin_date")).strftime("%d/%m/%Y")
        s = checkin.get("sleep", {})
        lines.append(f"{date}: {s.get('sleep_duration_hours', 0):.1f}h | Qualidade {s.get('sleep_quality_rating', 0)}/5 | {s.get('sleep_start_time', '--:--')}-{s.get('sleep_end_time', '--:--')}")
    return "\n".join(lines)

def _parse_previous_week_data(past_reports: list) -> str:
    """Formats past report data by parsing its HTML content."""
    if not past_reports: return "Nenhum relatório anterior encontrado para comparação.\n"
    try:
        soup = BeautifulSoup(past_reports[0].get("html_content", ""), 'html.parser')
        metrics = soup.find_all('div', class_='metric-item')
        data = {"Calorias médias": "N/A", "Proteína média": "N/A", "Volume total": "N/A"}
        for metric in metrics:
            label = metric.find('div', class_='metric-label').text.strip().lower()
            value = metric.find('div', class_='metric-value').text.strip()
            if 'calorias médias' in label: data["Calorias médias"] = value
            elif 'proteína média' in label: data["Proteína média"] = value
            elif 'volume total' in label: data["Volume total"] = value
        return f"Calorias médias: {data['Calorias médias']}\nProteína média: {data['Proteína média']}\nVolume treino: {data['Volume total']}"
    except Exception as e:
        logger.error(f"Error parsing previous report HTML: {e}")
        return "Erro ao processar dados da semana anterior.\n"

async def create_report_for_student(student_id: str, db: AsyncIOMotorDatabase) -> str:
    """Orchestrates the report generation for a specific student and returns HTML."""
    logger.info(f"Starting report creation for student_id: {student_id}")
    if not ObjectId.is_valid(student_id): raise HTTPException(status_code=400, detail=f"Invalid student ID: {student_id}")

    student_obj_id = ObjectId(student_id)
    student_data = await db["students"].find_one({"_id": student_obj_id})
    if not student_data: raise HTTPException(status_code=404, detail=f"Student with ID {student_id} not found")

    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=7)

    checkins_data = await db["checkins"].find({"student_id": student_obj_id, "checkin_date": {"$gte": start_date.strftime("%Y-%m-%d"), "$lte": end_date.strftime("%Y-%m-%d")}}).to_list(length=None)
    macro_goals_data = await db["macro_goals"].find_one({"student_id": student_obj_id}) or {}
    past_reports_data = await db["relatorios"].find({"student_id": student_obj_id}).sort("generated_at", -1).limit(1).to_list(length=1)
    logger.info(f"Data fetched for student_id: {student_id}. Found {len(checkins_data)} check-ins.")

    formatted_data_for_prompt = _analyze_and_format_data(checkins_data, student_data, past_reports_data, macro_goals_data)
    logger.debug(f"Formatted data for prompt for student_id: {student_id}")

    final_html_output = await generate_report_content(formatted_data_for_prompt)
    logger.info(f"Agent successfully generated HTML content for student_id: {student_id}")

    new_report = {"student_id": student_obj_id, "generated_at": datetime.now(UTC), "html_content": final_html_output}
    await db["relatorios"].insert_one(new_report)
    logger.info(f"Successfully saved new report for student_id: {student_id}")

    return final_html_output