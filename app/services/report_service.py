import logging
import re
from bson import ObjectId
from datetime import datetime, UTC, timedelta
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from bs4 import BeautifulSoup
import numpy as np
from app.core.config import settings

from app.agents.report_generator_agent import generate_report_section

logger = logging.getLogger(__name__)

def _get_base_context(checkins: list, student: dict, past_reports: list, macro_goals: dict) -> str:
    """Analyzes all weekly data and formats it into a single string for the LLM prompt context."""
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

    context = f"""
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
    return context

def _parse_training_journal(journal: str) -> str:
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
    if not checkins: return "Nenhum treino registrado na semana.\n"
    lines = []
    for checkin in checkins:
        date = datetime.fromisoformat(checkin.get("checkin_date")).strftime("%d/%m/%Y")
        journal = checkin.get("training", {}).get("training_journal", "")
        if journal: lines.append(f"**{date}**\n{_parse_training_journal(journal)}")
    return "\n\n".join(lines)

def _format_nutrition_data(checkins: list) -> str:
    if not checkins: return "Nenhum dado de nutrição registrado na semana.\n"
    lines = []
    for checkin in checkins:
        date = datetime.fromisoformat(checkin.get("checkin_date")).strftime("%d/%m/%Y")
        n = checkin.get("nutrition", {})
        lines.append(f"{date}: {n.get('calories', 0)}kcal | {n.get('protein', 0)}g | {n.get('carbs', 0)}g | {n.get('fat', 0)}g")
    return "\n".join(lines)

def _format_sleep_data(checkins: list) -> str:
    if not checkins: return "Nenhum dado de sono registrado na semana.\n"
    lines = []
    for checkin in checkins:
        date = datetime.fromisoformat(checkin.get("checkin_date")).strftime("%d/%m/%Y")
        s = checkin.get("sleep", {})
        lines.append(f"{date}: {s.get('sleep_duration_hours', 0):.1f}h | Qualidade {s.get('sleep_quality_rating', 0)}/5 | {s.get('sleep_start_time', '--:--')}-{s.get('sleep_end_time', '--:--')}")
    return "\n".join(lines)

def _parse_previous_week_data(past_reports: list) -> str:
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
    """Orchestrates the report generation by calling multiple specialist agents and populating a template."""
    logger.info(f"Starting orchestrated report creation for student_id: {student_id}")
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

    base_context = _get_base_context(checkins_data, student_data, past_reports_data, macro_goals_data)

    # --- Generate content for each section ---
    overview_content = await generate_report_section("overview", base_context)
    nutrition_html_content = await _build_nutrition_section(checkins_data, macro_goals_data, past_reports_data, base_context)

    # --- Load the HTML template ---
    with open(settings.REPORT_TEMPLATE_FILE, "r", encoding="utf-8") as f:
        report_html = f.read()

    # --- Populate the template ---
    report_html = report_html.replace("{{student_name}}", student_data.get('name', 'N/A'))
    report_html = report_html.replace("{{week_string}}", f"Semana {end_date.isocalendar()[1]} ({start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m')})")
    report_html = report_html.replace("{{overview_section}}", f"<p>{overview_content}</p>")
    report_html = report_html.replace("{{nutrition_analysis_section}}", nutrition_html_content)
    
    # For now, fill other sections with placeholders
    report_html = report_html.replace("{{score_cards}}", "<!-- Score cards to be implemented -->")
    report_html = report_html.replace("{{sleep_analysis_section}}", "<!-- Sleep analysis to be implemented -->")
    report_html = report_html.replace("{{training_analysis_section}}", "<!-- Training analysis to be implemented -->")
    report_html = report_html.replace("{{detailed_insights_section}}", "<!-- Detailed insights to be implemented -->")
    report_html = report_html.replace("{{recommendations_section}}", "<!-- Recommendations to be implemented -->")
    report_html = report_html.replace("{{conclusion_section}}", "<!-- Conclusion to be implemented -->")
    report_html = report_html.replace("{{next_week_string}}", f"Semana {end_date.isocalendar()[1] + 1}")
    report_html = report_html.replace("{{generation_date}}", end_date.strftime("%d de %B de %Y"))

    # --- Save and return the final report ---
    new_report = {"student_id": student_obj_id, "generated_at": datetime.now(UTC), "html_content": report_html}
    await db["relatorios"].insert_one(new_report)
    logger.info(f"Successfully saved new orchestrated report for student_id: {student_id}")

    return report_html


async def _build_nutrition_section(checkins: list, macro_goals: dict, past_reports: list, base_context_for_llm: str) -> str:
    """Builds the entire HTML block for the nutrition analysis section."""
    # 1. Analyze current week data
    daily_nutrition = [c.get('nutrition', {}) for c in checkins]
    calories = [n.get('calories', 0) for n in daily_nutrition if n.get('calories', 0) > 0]
    proteins = [n.get('protein', 0) for n in daily_nutrition if n.get('protein', 0) > 0]
    carbs = [n.get('carbs', 0) for n in daily_nutrition if n.get('carbs', 0) > 0]
    fats = [n.get('fat', 0) for n in daily_nutrition if n.get('fat', 0) > 0]

    avg_calories = np.mean(calories) if calories else 0
    avg_proteins = np.mean(proteins) if proteins else 0
    avg_carbs = np.mean(carbs) if carbs else 0
    avg_fats = np.mean(fats) if fats else 0
    calorie_cv = (np.std(calories) / avg_calories) * 100 if avg_calories > 0 else 0
    protein_goal = macro_goals.get('protein', 1)
    days_on_protein_goal = sum(1 for p in proteins if abs(p - protein_goal) <= 10)

    # 2. Get previous week data for comparison
    prev_week_metrics = _parse_previous_week_metrics(past_reports)
    
    # 3. Build the HTML for the metrics grids
    metrics_grid_1 = _build_main_metrics_grid(avg_calories, avg_proteins, avg_carbs, avg_fats, protein_goal, prev_week_metrics)
    metrics_grid_2 = _build_consistency_metrics_grid(calorie_cv, days_on_protein_goal, len(calories))
    
    # 4. Build the HTML for the daily table
    daily_table = _build_daily_nutrition_table(checkins)
    
    # 5. Generate LLM insights
    llm_insights = await generate_report_section("nutrition_analysis", base_context_for_llm)
    
    # 6. Combine all parts into a single HTML block
    return f"""{metrics_grid_1}
{metrics_grid_2}
<h3>Distribuição Calórica Diária</h3>
{daily_table}
{llm_insights}"""

def _build_main_metrics_grid(avg_cals, avg_prot, avg_carbs, avg_fats, prot_goal, prev_metrics) -> str:
    # Helper to create comparison strings
    def get_comparison_html(current, previous, unit='kcal', invert_color=False):
        if previous == 0: return ""
        diff = current - previous
        perc_diff = (diff / previous) * 100
        color = 'positive' if (diff > 0 and not invert_color) or (diff < 0 and invert_color) else 'critical'
        sign = '+' if diff > 0 else ''
        return f'<div class="metric-comparison">vs. semana anterior: <span class="{color}">{sign}{diff:.0f} {unit} ({sign}{perc_diff:.1f}%)</span></div>'

    cal_comp = get_comparison_html(avg_cals, prev_metrics.get('calories', 0), unit='kcal', invert_color=True)
    prot_comp = get_comparison_html(avg_prot, prev_metrics.get('protein', 0), unit='g')

    prot_adherence = (avg_prot / prot_goal) * 100 if prot_goal > 0 else 0

    return f"""<div class="metrics-grid">
        <div class="metric-item">
            <div class="metric-label">Calorias Médias</div>
            <div class="metric-value">{avg_cals:.0f} kcal</div>
            {cal_comp}
        </div>
        <div class="metric-item">
            <div class="metric-label">Proteína Média</div>
            <div class="metric-value">{avg_prot:.0f}g</div>
            <div class="metric-comparison">Meta: {prot_goal:.0f}g | <span class="positive">{prot_adherence:.1f}%</span></div>
            {prot_comp}
        </div>
        <div class="metric-item">
            <div class="metric-label">Carboidratos Médios</div>
            <div class="metric-value">{avg_carbs:.0f}g</div>
            <div class="metric-comparison">{avg_carbs*4/avg_cals*100 if avg_cals > 0 else 0:.0f}% das calorias totais</div>
        </div>
        <div class="metric-item">
            <div class="metric-label">Gordura Média</div>
            <div class="metric-value">{avg_fats:.0f}g</div>
            <div class="metric-comparison">{avg_fats*9/avg_cals*100 if avg_cals > 0 else 0:.0f}% das calorias totais</div>
        </div>
    </div>"""

def _build_consistency_metrics_grid(cv, days_on_goal, total_days) -> str:
    return f"""<h3>Consistência Nutricional</h3>
    <div class="metrics-grid">
        <div class="metric-item">
            <div class="metric-label">Coeficiente de Variação</div>
            <div class="metric-value">{cv:.1f}%</div>
            <div class="metric-comparison"><span class="positive">Excelente consistência</span></div>
        </div>
        <div class="metric-item">
            <div class="metric-label">Dias na Meta Proteica</div>
            <div class="metric-value">{days_on_goal}/{total_days}</div>
            <div class="metric-comparison"><span class="positive">{days_on_goal/total_days*100 if total_days > 0 else 0:.0f}% de aderência</span></div>
        </div>
    </div>"""

def _build_daily_nutrition_table(checkins: list) -> str:
    rows = []
    for checkin in checkins:
        date = datetime.fromisoformat(checkin.get("checkin_date")).strftime("%d/%m (%a)")
        n = checkin.get("nutrition", {})
        rows.append(f"""<tr>
            <td>{date}</td>
            <td>{n.get('calories', 0)} kcal</td>
            <td>{n.get('protein', 0)}g</td>
            <td>{n.get('carbs', 0)}g</td>
            <td>{n.get('fat', 0)}g</td>
            <td><span class="positive">Meta</span></td>
        </tr>""")
    
    table_rows = "\n".join(rows)
    return f"""<table>
        <thead>
            <tr><th>Data</th><th>Calorias</th><th>Proteína</th><th>Carbos</th><th>Gordura</th><th>Status</th></tr>
        </thead>
        <tbody>
            {table_rows}
        </tbody>
    </table>"""

def _parse_previous_week_metrics(past_reports: list) -> dict:
    if not past_reports: return {}
    try:
        soup = BeautifulSoup(past_reports[0].get("html_content", ""), 'html.parser')
        metrics = {}
        # Simplified parsing logic
        for metric_item in soup.find_all('div', class_='metric-item'):
            label = metric_item.find('div', class_='metric-label').text.strip().lower()
            value_str = metric_item.find('div', class_='metric-value').text.strip()
            value = float(re.sub(r'[^0-9.]', '', value_str))
            if 'calorias' in label: metrics['calories'] = value
            if 'proteína' in label: metrics['protein'] = value
        return metrics
    except Exception as e:
        logger.error(f"Error parsing previous report for metrics: {e}")
        return {}