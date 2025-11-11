import logging
import re
import locale
import base64
import os
from bson import ObjectId
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from bs4 import BeautifulSoup
import numpy as np
from app.core.config import settings

from app.agents.report_generator_agent import generate_report_section

logger = logging.getLogger(__name__)

MONTHS_PT = {
    'January': 'Janeiro',
    'February': 'Fevereiro',
    'March': 'Março',
    'April': 'Abril',
    'May': 'Maio',
    'June': 'Junho',
    'July': 'Julho',
    'August': 'Agosto',
    'September': 'Setembro',
    'October': 'Outubro',
    'November': 'Novembro',
    'December': 'Dezembro'
}

def _infer_training_sessions_per_week(historical_checkins: list) -> int:
    """
    Infers the number of expected training sessions per week by finding the
    maximum number of workouts performed in any single week over the given history.
    """
    if not historical_checkins:
        logger.warning("No historical check-ins found to infer training sessions. Defaulting to 5.")
        return 5

    trainings_per_week = {}
    for checkin in historical_checkins:
        journal = checkin.get('training', {}).get('training_journal', '').strip().lower()
        if journal and journal not in ('', 'não treinei hoje'):
            checkin_date = datetime.fromisoformat(checkin.get("checkin_date"))
            year, week, _ = checkin_date.isocalendar()
            week_key = f"{year}-{week}"
            
            trainings_per_week[week_key] = trainings_per_week.get(week_key, 0) + 1

    if not trainings_per_week:
        logger.warning("No valid training sessions found in history to infer split. Defaulting to 5.")
        return 5

    max_sessions = max(trainings_per_week.values())
    logger.info(f"Inferred training split: {max_sessions} sessions per week based on historical maximum.")
    return max_sessions

def _get_base_context(checkins: list, student: dict, past_reports: list, macro_goals: dict) -> str:
    """Analyzes all weekly data and formats it into a single string for the LLM prompt context."""
    daily_nutrition = [c.get('nutrition', {}) for c in checkins]
    calories = [n.get('calories', 0) for n in daily_nutrition if n.get('calories', 0) > 0]
    proteins = [n.get('protein', 0) for n in daily_nutrition if n.get('protein', 0) > 0]
    avg_calories = np.mean(calories) if calories else 0
    avg_proteins = np.mean(proteins) if proteins else 0
    calorie_cv = (np.std(calories) / avg_calories) * 100 if avg_calories > 0 else 0

    # Extract all macro goals
    calories_goal = macro_goals.get('calories', 0)
    protein_goal = macro_goals.get('protein', 0)
    carbs_goal = macro_goals.get('carbs', 0)
    fat_goal = macro_goals.get('fat', 0)

    protein_adherence = (avg_proteins / protein_goal) * 100 if protein_goal > 0 else 0

    daily_sleep = [c.get('sleep', {}) for c in checkins]
    sleep_hours = [s.get('sleep_duration_hours', 0) for s in daily_sleep if s.get('sleep_duration_hours', 0) > 0]
    avg_sleep_hours = np.mean(sleep_hours) if sleep_hours else 0
    total_sets = _calculate_total_sets(checkins)
    previous_week_data = _parse_previous_week_data(past_reports)
    
    user_tz = timezone(timedelta(hours=-3))
    end_date = datetime.now(user_tz)
    start_date = end_date - timedelta(days=7)
    week_number = end_date.isocalendar()[1]
    month_name_en = end_date.strftime("%B")
    month_name_pt = MONTHS_PT.get(month_name_en, month_name_en)
    week_str = f"Semana {week_number} de {month_name_pt} {end_date.year} ({start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m')})"

    context = f"""
# CONTEXTO BASE - DADOS BRUTOS E ANÁLISE PRELIMINAR

ALUNO: {student.get('full_name', 'N/A')}
SEMANA: {week_str}

## DADOS BRUTOS DA SEMANA
TREINOS:
{_format_training_data(checkins)}
NUTRIÇÃO DIÁRIA:
{_format_nutrition_data(checkins)}
SONO DIÁRIO:
{_format_sleep_data(checkins)}

## METAS NUTRICIONAIS
- Calorias: {calories_goal} kcal
- Proteína: {protein_goal}g
- Carboidratos: {carbs_goal}g
- Gorduras: {fat_goal}g

## DADOS ANALÍTICOS
### RESUMO NUTRICIONAL
- Calorias Médias: {avg_calories:.0f} kcal
- Proteína Média: {avg_proteins:.0f}g (Aderência: {protein_adherence:.0f}%)
- Coeficiente de Variação (Calorias): {calorie_cv:.1f}%

### RESUMO SONO
- Média de Sono: {avg_sleep_hours:.1f} horas/noite

### RESUMO TREINO
- Volume Total (Séries): {total_sets} séries

## DADOS SEMANA ANTERIOR (para comparação):
{previous_week_data}

CONTEXTO ADICIONAL DO ALUNO:
{student.get('additional_context', 'Nenhum contexto adicional fornecido.')}
"""
    return context

def _format_training_data(checkins: list) -> str:
    if not checkins: return "Nenhum treino registrado na semana.\n"
    lines = []
    for checkin in checkins:
        date = datetime.fromisoformat(checkin.get("checkin_date")).strftime("%d/%m/%Y")
        journal = checkin.get("training", {}).get("training_journal", "")
        if journal: lines.append(f"**{date}**\n{journal}")
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
    try:
        locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
    except locale.Error:
        logger.warning("Locale pt_BR.UTF-8 not available. Date formatting may be in English.")

    logger.info(f"Starting orchestrated report creation for student_id: {student_id}")
    if not ObjectId.is_valid(student_id): raise HTTPException(status_code=400, detail=f"Invalid student ID: {student_id}")

    student_obj_id = ObjectId(student_id)
    student_data = await db["students"].find_one({"_id": student_obj_id})
    if not student_data:
        raise HTTPException(status_code=404, detail=f"Student with ID {student_id} not found")
    
    student_name = student_data.get('full_name', 'N/A')
    logger.info(f"Student data found: {student_data}")
    logger.info(f"Gerando relatório para {student_name}")

    # Define date ranges
    user_tz = timezone(timedelta(hours=-3))
    end_date = datetime.now(user_tz)
    start_date = end_date - timedelta(days=7)
    history_start_date = end_date - timedelta(weeks=6)

    # Fetch data for the current week
    checkins_data = await db["checkins"].find({
        "student_id": student_obj_id, 
        "checkin_date": {
            "$gte": start_date.strftime("%Y-%m-%d"), 
            "$lte": end_date.strftime("%Y-%m-%d")
        }
    }).to_list(length=None)

    # Fetch data for the last 6 weeks to infer training split
    historical_checkins = await db["checkins"].find({
        "student_id": student_obj_id,
        "checkin_date": {
            "$gte": history_start_date.strftime("%Y-%m-%d"),
            "$lte": end_date.strftime("%Y-%m-%d")
        }
    }).to_list(length=None)

    total_sessions_expected = _infer_training_sessions_per_week(historical_checkins)

    macro_goals_data = await db["macro_goals"].find_one({"student_id": student_obj_id}) or {}
    past_reports_data = await db["relatorios"].find({"student_id": student_obj_id}).sort("generated_at", -1).limit(1).to_list(length=1)
    logger.info(f"Data fetched for student_id: {student_id}. Found {len(checkins_data)} check-ins for the week.")

    # --- Chained Context Start ---
    chained_context = _get_base_context(checkins_data, student_data, past_reports_data, macro_goals_data)

    overview_content = await generate_report_section("overview", chained_context, student_name)
    chained_context += f"\n\n# SEÇÃO GERADA: Visão Geral da Semana\n{overview_content}"

    nutrition_html_content = await _build_nutrition_section(checkins_data, macro_goals_data, past_reports_data, chained_context, student_name)
    chained_context += f"\n\n# SEÇÃO GERADA: Análise Nutricional\n{nutrition_html_content}"

    sleep_html_content = await _build_sleep_analysis_section(checkins_data, chained_context, student_name)
    chained_context += f"\n\n# SEÇÃO GERADA: Análise de Sono e Recuperação\n{sleep_html_content}"

    training_html_content = await _build_training_analysis_section(checkins_data, chained_context, student_name, total_sessions_expected)
    chained_context += f"\n\n# SEÇÃO GERADA: Desempenho nos Treinos\n{training_html_content}"

    score_cards_html_content = _build_score_cards_section(checkins_data, macro_goals_data, total_sessions_expected)

    detailed_insights_html_content = await generate_report_section("detailed_insights", chained_context, student_name)
    chained_context += f"\n\n# SEÇÃO GERADA: Insights Detalhados\n{detailed_insights_html_content}"

    recommendations_html_content = await generate_report_section("recommendations", chained_context, student_name)
    chained_context += f"\n\n# SEÇÃO GERADA: Recomendações e Ajustes\n{recommendations_html_content}"

    conclusion_html_content = await generate_report_section("conclusion", chained_context, student_name)
    # --- Chained Context End ---

    # Read logo and encode it in Base64
    logo_data_uri = ""
    try:
        with open("app/static/img/logo.png", "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            logo_data_uri = f"data:image/png;base64,{encoded_string}"
    except FileNotFoundError:
        logger.warning("Logo file not found at app/static/img/logo.png. Report will be generated without a logo.")

    with open(settings.REPORT_TEMPLATE_FILE, "r", encoding="utf-8") as f:
        report_html = f.read()

    month_name_en = end_date.strftime("%B")
    month_name_pt = MONTHS_PT.get(month_name_en, month_name_en)

    report_html = report_html.replace("{{logo_data_uri}}", logo_data_uri)
    report_html = report_html.replace("{{student_name}}", student_name)
    report_html = report_html.replace("{{week_string}}", f"Semana {end_date.isocalendar()[1]} ({start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m')})")
    report_html = report_html.replace("{{overview_section}}", f"<p>{overview_content}</p>")
    report_html = report_html.replace("{{nutrition_analysis_section}}", nutrition_html_content)
    report_html = report_html.replace("{{sleep_analysis_section}}", sleep_html_content)
    report_html = report_html.replace("{{training_analysis_section}}", training_html_content)
    report_html = report_html.replace("{{score_cards}}", score_cards_html_content)
    report_html = report_html.replace("{{detailed_insights_section}}", detailed_insights_html_content)
    report_html = report_html.replace("{{recommendations_section}}", recommendations_html_content)
    report_html = report_html.replace("{{conclusion_section}}", conclusion_html_content)
    report_html = report_html.replace("{{next_week_string}}", f"Semana {end_date.isocalendar()[1] + 1}")
    report_html = report_html.replace("{{generation_date}}", f"{end_date.day} de {month_name_pt} de {end_date.year}")

    # --- Save report to local file ---
    try:
        today_str = end_date.strftime("%Y-%m-%d")
        save_dir = os.path.join("relatorios_gerados", today_str)
        os.makedirs(save_dir, exist_ok=True)

        week_number = end_date.isocalendar()[1]
        year = end_date.year
        filename = f"Relatorio_Semanal_{student_name.replace(' ', '_')}_Semana{week_number}_{year}.html"
        save_path = os.path.join(save_dir, filename)

        with open(save_path, "w", encoding="utf-8") as f:
            f.write(report_html)
        logger.info(f"Report successfully saved to local file: {save_path}")

    except Exception as e:
        logger.error(f"Failed to save report to local file for student {student_id}: {e}")

    # --- Save report to database ---
    new_report = {"student_id": student_obj_id, "generated_at": datetime.now(timezone.utc), "html_content": report_html}
    await db["relatorios"].insert_one(new_report)
    logger.info(f"Successfully saved new orchestrated report for student_id: {student_id}")

async def generate_bulk_reports(db: AsyncIOMotorDatabase):
    """Fetches all active students and generates their reports in parallel."""
    logger.info("--- Starting Bulk Report Generation --- ")
    
    try:
        active_students = await db["students"].find({"status": "active"}).to_list(length=None)
        if not active_students:
            logger.warning("No active students found. Aborting bulk generation.")
            return

        logger.info(f"Found {len(active_students)} active students. Starting parallel generation...")

        tasks = [create_report_for_student(str(student["_id"]), db) for student in active_students]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = 0
        failure_count = 0

        for i, result in enumerate(results):
            student_name = active_students[i].get('full_name', 'Unknown')
            if isinstance(result, Exception):
                failure_count += 1
                logger.error(f"Failed to generate report for {student_name}: {result}")
            else:
                success_count += 1
                logger.info(f"Successfully generated report for {student_name}")

        logger.info(f"--- Bulk Report Generation Finished ---")
        logger.info(f"Summary: {success_count} successful, {failure_count} failed.")

    except Exception as e:
        logger.critical(f"A critical error occurred during the bulk generation process: {e}")

    return report_html

async def _build_nutrition_section(checkins: list, macro_goals: dict, past_reports: list, chained_context: str, student_name: str) -> str:
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
    prev_week_metrics = _parse_previous_week_metrics(past_reports)
    metrics_grid_1 = _build_main_metrics_grid(avg_calories, avg_proteins, avg_carbs, avg_fats, protein_goal, prev_week_metrics)
    metrics_grid_2 = _build_consistency_metrics_grid(calorie_cv, days_on_protein_goal, len(calories))
    daily_table = _build_daily_nutrition_table(checkins, macro_goals)
    llm_insights = await generate_report_section("nutrition_analysis", chained_context, student_name)
    return f"""
{metrics_grid_1}
{metrics_grid_2}
<h3>Distribuição Calórica Diária</h3>
{daily_table}
{llm_insights}"""

def _build_main_metrics_grid(avg_cals, avg_prot, avg_carbs, avg_fats, prot_goal, prev_metrics) -> str:

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

    return f"""
<div class="metrics-grid">

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
    return f"""
<h3>Consistência Nutricional</h3>
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

def _build_daily_nutrition_table(checkins: list, macro_goals: dict) -> str:
    rows = []
    # Get macro goals for comparison
    calories_goal = macro_goals.get('calories', 0)
    protein_goal = macro_goals.get('protein', 0)
    carbs_goal = macro_goals.get('carbs', 0)
    fat_goal = macro_goals.get('fat', 0)

    for checkin in checkins:
        date = datetime.fromisoformat(checkin.get("checkin_date")).strftime("%d/%m (%a)")
        n = checkin.get("nutrition", {})
        
        current_calories = n.get('calories', 0)
        current_protein = n.get('protein', 0)
        current_carbs = n.get('carbs', 0)
        current_fat = n.get('fat', 0)

        # Determine status based on goals (example logic, can be refined)
        status = "Meta"
        status_class = "positive"

        # Define a tolerance for being "near" the goal, e.g., +/- 10%
        CAL_TOLERANCE_PERCENT = 0.10
        PROT_TOLERANCE_PERCENT = 0.10
        CARBS_TOLERANCE_PERCENT = 0.10
        FAT_TOLERANCE_PERCENT = 0.10

        # Check calories
        if calories_goal > 0 and not (calories_goal * (1 - CAL_TOLERANCE_PERCENT) <= current_calories <= calories_goal * (1 + CAL_TOLERANCE_PERCENT)):
            status = "Atenção"
            status_class = "warning"
        
        # Check protein (more critical for protein)
        if protein_goal > 0 and not (protein_goal * (1 - PROT_TOLERANCE_PERCENT) <= current_protein <= protein_goal * (1 + PROT_TOLERANCE_PERCENT)):
            status = "Atenção"
            status_class = "warning"
            if current_protein < protein_goal * (1 - PROT_TOLERANCE_PERCENT): # Significantly below protein goal
                status = "Crítico"
                status_class = "critical"

        # Check carbs and fat (less critical, can be adjusted)
        if carbs_goal > 0 and not (carbs_goal * (1 - CARBS_TOLERANCE_PERCENT) <= current_carbs <= carbs_goal * (1 + CARBS_TOLERANCE_PERCENT)):
            if status_class != "critical": # Don't override critical
                status = "Atenção"
                status_class = "warning"
        
        if fat_goal > 0 and not (fat_goal * (1 - FAT_TOLERANCE_PERCENT) <= current_fat <= fat_goal * (1 + FAT_TOLERANCE_PERCENT)):
            if status_class != "critical": # Don't override critical
                status = "Atenção"
                status_class = "warning"

        rows.append(f"""
<tr>
            <td>{date}</td>
            <td>{current_calories} kcal</td>
            <td>{current_protein}g</td>
            <td>{current_carbs}g</td>
            <td>{current_fat}g</td>
            <td><span class=\"{status_class}\">{status}</span></td>
        </tr>""")
    table_rows = "\n".join(rows)
    return f"""
<table>
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
        for metric_item in soup.find_all('div', class_='metric-item'):
            label = metric_item.find('div', class_='metric-label').text.strip().lower()
            value_str = metric_item.find('div', class_='metric-value').text.strip()
            try:
                value = float(re.sub(r'[^0-9.]', '', value_str))
            except (ValueError, TypeError):
                value = 0
            if 'calorias' in label: metrics['calories'] = value
            if 'proteína' in label: metrics['protein'] = value
        return metrics
    except Exception as e:
        logger.error(f"Error parsing previous report for metrics: {e}")
        return {}

async def _build_sleep_analysis_section(checkins: list, chained_context: str, student_name: str) -> str:
    daily_table = _build_daily_sleep_table(checkins)
    llm_insights = await generate_report_section("sleep_analysis", chained_context, student_name)
    return f"""
{daily_table}
{llm_insights}"""

def _build_daily_sleep_table(checkins: list) -> str:
    rows = []
    for checkin in checkins:
        date = datetime.fromisoformat(checkin.get("checkin_date")).strftime("%d/%m (%a)")
        s = checkin.get("sleep", {})
        status = "Adequado" if s.get('sleep_duration_hours', 0) >= 7 else "Limite inferior"
        status_class = "positive" if status == "Adequado" else "warning"
        rows.append(f"""
t<tr>
            <td>{date}</td>
            <td>{s.get('sleep_duration_hours', 0):.1f}h</td>
            <td>{s.get('sleep_quality_rating', 0)}/5</td>
            <td>{s.get('sleep_start_time', '--:--')} - {s.get('sleep_end_time', '--:--')}</td>
            <td><span class=\"{status_class}\">{status}</span></td>
        </tr>""")
    table_rows = "\n".join(rows)
    return f"""
<table>
        <thead>
            <tr><th>Data</th><th>Duração</th><th>Qualidade</th><th>Horário</th><th>Status</th></tr>
        </thead>
        <tbody>
            {table_rows}
        </tbody>
    </table>"""

async def _build_training_analysis_section(checkins: list, chained_context: str, student_name: str, total_sessions_expected: int) -> str:
    training_checkins = [c for c in checkins if c.get('training', {}).get('training_journal', '').strip().lower() not in ('', 'não treinei hoje')]
    sessions_performed = len(training_checkins)
    total_sets = _calculate_total_sets(checkins)
    adherence_percentage = (sessions_performed / total_sessions_expected * 100) if total_sessions_expected > 0 else 0

    metrics_grid = f"""
<div class="metrics-grid">
        <div class="metric-item">
            <div class="metric-label">Sessões Realizadas</div>
            <div class="metric-value">{sessions_performed}/{total_sessions_expected}</div>
            <div class="metric-comparison">Aderência: <span class="positive">{adherence_percentage:.0f}%</span></div>
        </div>
        <div class="metric-item">
            <div class="metric-label">Volume Semanal</div>
            <div class="metric-value">~{total_sets} séries</div>
            <div class="metric-comparison">Distribuição completa A-E</div>
        </div>
    </div>"""
    training_details_html = _build_training_details(training_checkins)
    llm_insights = await generate_report_section("training_analysis", chained_context, student_name)
    return f"""
{metrics_grid}
<h3>Detalhamento dos Treinos</h3>
{training_details_html}
{llm_insights}"""

def _calculate_total_sets(checkins: list) -> int:
    total_sets = 0
    for checkin in checkins:
        journal = checkin.get('training', {}).get('training_journal', '')
        total_sets += len(re.findall(r'série', journal, re.IGNORECASE))
    return total_sets

def _build_training_details(checkins: list) -> str:
    details = []
    for checkin in checkins:
        date = datetime.fromisoformat(checkin.get("checkin_date"))
        training_data = checkin.get('training', {})
        journal = training_data.get('training_journal', '')
        observation = training_data.get('student_observation', 'Sem observações relatadas')

        if not journal or journal.strip().lower() == "não treinei hoje":
            continue

        lines = journal.strip().split('\n')
        
        # A primeira linha é o nome do treino, ex: "A - Peito e Ombro"
        training_name = lines.pop(0).strip() if lines else 'Treino'
        # A segunda linha é a data, que já temos, então podemos ignorar
        if lines and re.match(r'\w+day, \w+ \d+, \d+', lines[0]):
            lines.pop(0)

        exercises_html = ""
        current_exercise = None

        for line in lines:
            line = line.strip()
            if not line or "@hevyapp" in line or "hevy.com" in line:
                continue

            # Se a linha não começa com "Série", é um novo exercício
            if not line.lower().startswith('série'):
                if current_exercise:
                    exercises_html += f"<strong>{current_exercise}</strong><br>"
                current_exercise = line
            else:
                # É uma linha de série, anexa ao exercício atual
                if not current_exercise:
                    current_exercise = "Exercícios Diversos"
                exercises_html += f"• {line}<br>"
        
        # Adiciona o último exercício processado
        if current_exercise:
            exercises_html += f"<strong>{current_exercise}</strong><br>"

        details.append(f"""
<div class="training-detail manter-junto">
            <strong>{training_name} ({date.strftime("%d/%m - %A")})</strong><br>
            <em>Principais exercícios:</em><br>
            {exercises_html}
            <em>Observação:</em> "{observation}"
        </div>""")

    return "\n".join(details)

def _build_score_cards_section(checkins: list, macro_goals: dict, total_sessions_expected: int) -> str:
    # --- Sleep Score ---
    daily_sleep = [c.get('sleep', {}) for c in checkins]
    sleep_hours = [s.get('sleep_duration_hours', 0) for s in daily_sleep if s.get('sleep_duration_hours', 0) > 0]
    avg_sleep_hours = np.mean(sleep_hours) if sleep_hours else 0
    sleep_quality = [s.get('sleep_quality_rating', 0) for s in daily_sleep if s.get('sleep_quality_rating', 0) > 0]
    avg_sleep_quality = np.mean(sleep_quality) if sleep_quality else 0
    days_less_than_6h = sum(1 for s in sleep_hours if s < 6)

    rec_score = 0
    rec_status_class = "critical"
    if not sleep_hours:
        rec_score = 0
    elif avg_sleep_hours >= 7 and avg_sleep_quality >= 4 and days_less_than_6h == 0:
        rec_score = 9
        rec_status_class = "positive"
    elif avg_sleep_hours >= 6.5 and avg_sleep_quality >= 3.5 and days_less_than_6h <= 1:
        rec_score = 7
        rec_status_class = "warning"
    else:
        rec_score = 5

    # --- Performance Score ---
    training_checkins = [c for c in checkins if c.get('training', {}).get('training_journal', '').strip().lower() not in ('', 'não treinei hoje')]
    sessions_performed = len(training_checkins)
    training_adherence = (sessions_performed / total_sessions_expected) * 100 if total_sessions_expected > 0 else 0

    perf_score = 0
    perf_status_class = "critical"
    if not training_checkins and sessions_performed == 0:
        perf_score = 0
    elif training_adherence >= 100:
        perf_score = 10
        perf_status_class = "positive"
    elif training_adherence >= 80:
        perf_score = 8
        perf_status_class = "warning"
    else:
        perf_score = 6

    # --- Nutrition Score ---
    daily_nutrition = [c.get('nutrition', {}) for c in checkins]
    proteins = [n.get('protein', 0) for n in daily_nutrition if n.get('protein', 0) > 0]
    protein_goal = macro_goals.get('protein', 1)
    avg_proteins = np.mean(proteins) if proteins else 0
    protein_adherence_days = sum(1 for p in proteins if abs(p - protein_goal) <= 10)
    total_nutrition_days = len(proteins)

    nutri_score = 0
    nutri_status_class = "critical"
    if not proteins:
        nutri_score = 0
    elif protein_adherence_days >= total_nutrition_days * 0.8 and total_nutrition_days > 0:
        nutri_score = 8
        nutri_status_class = "warning"
        if protein_adherence_days == total_nutrition_days and avg_proteins >= protein_goal * 0.95:
            nutri_score = 10
            nutri_status_class = "positive"
    else:
        nutri_score = 6
    rec_card = f"""
<div class="score-card {rec_status_class}">
        <div class="score-label">Recuperação</div>
        <div class="score-value">{rec_score}/10</div>
        <div class="score-detail">Sono: {avg_sleep_hours:.1f}h média<br>Qualidade: {avg_sleep_quality:.1f}/5<br>{days_less_than_6h} dias <6h</div>
    </div>"""
    perf_card = f"""
<div class="score-card {perf_status_class}">
        <div class="score-label">Desempenho</div>
        <div class="score-value">{perf_score}/10</div>
        <div class="score-detail">Aderência: {training_adherence:.0f}%<br>{sessions_performed}/{total_sessions_expected} treinos realizados</div>
    </div>"""
    nutri_card = f"""
<div class="score-card {nutri_status_class}">
        <div class="score-label">Alimentação</div>
        <div class="score-value">{nutri_score}/10</div>
        <div class="score-detail">Proteína: {avg_proteins:.0f}g média<br>Aderência: {protein_adherence_days}/{total_nutrition_days} dias<br>Meta: {protein_goal}g</div>
    </div>"""
    return f"""
{rec_card}
{perf_card}
{nutri_card}"""
