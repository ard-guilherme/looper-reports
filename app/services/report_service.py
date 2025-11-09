import logging
import re
import locale
from bson import ObjectId
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from bs4 import BeautifulSoup
import numpy as np
from app.core.config import settings

from app.agents.report_generator_agent import generate_report_section

logger = logging.getLogger(__name__)

def _get_base_context(checkins: list, student: dict, past_reports: list, macro_goals: dict) -> str:
    """Analyzes all weekly data and formats it into a single string for the LLM prompt context."""
    daily_nutrition = [c.get('nutrition', {}) for c in checkins]
    calories = [n.get('calories', 0) for n in daily_nutrition if n.get('calories', 0) > 0]
    proteins = [n.get('protein', 0) for n in daily_nutrition if n.get('protein', 0) > 0]
    avg_calories = np.mean(calories) if calories else 0
    avg_proteins = np.mean(proteins) if proteins else 0
    calorie_cv = (np.std(calories) / avg_calories) * 100 if avg_calories > 0 else 0
    protein_goal = macro_goals.get('protein', 0)
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
    month_name = end_date.strftime("%B").capitalize()
    week_str = f"Semana {week_number} de {month_name} {end_date.year} ({start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m')})"

    context = f"""
ALUNO: {student.get('full_name', 'N/A')}
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
    logger.info(f"Student data found: {student_data}")
    logger.info(f"Gerando relatório para {student_data.get('full_name', 'N/A')}")

    user_tz = timezone(timedelta(hours=-3))
    end_date = datetime.now(user_tz)
    start_date = end_date - timedelta(days=7)

    checkins_data = await db["checkins"].find({
        "student_id": student_obj_id, 
        "checkin_date": {
            "$gte": start_date.strftime("%Y-%m-%d"), 
            "$lte": end_date.strftime("%Y-%m-%d")
        }
    }).to_list(length=None)
    macro_goals_data = await db["macro_goals"].find_one({"student_id": student_obj_id}) or {}
    past_reports_data = await db["relatorios"].find({"student_id": student_obj_id}).sort("generated_at", -1).limit(1).to_list(length=1)
    logger.info(f"Data fetched for student_id: {student_id}. Found {len(checkins_data)} check-ins.")

    base_context = _get_base_context(checkins_data, student_data, past_reports_data, macro_goals_data)

    overview_content = await generate_report_section("overview", base_context)
    nutrition_html_content = await _build_nutrition_section(checkins_data, macro_goals_data, past_reports_data, base_context)
    sleep_html_content = await _build_sleep_analysis_section(checkins_data, base_context)
    training_html_content = await _build_training_analysis_section(checkins_data, base_context)
    score_cards_html_content = _build_score_cards_section(checkins_data, macro_goals_data)
    detailed_insights_html_content = await generate_report_section("detailed_insights", base_context)
    recommendations_html_content = await generate_report_section("recommendations", base_context)
    conclusion_html_content = await generate_report_section("conclusion", base_context)

    with open(settings.REPORT_TEMPLATE_FILE, "r", encoding="utf-8") as f:
        report_html = f.read()

    report_html = report_html.replace("{{student_name}}", student_data.get('name', 'N/A'))
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
    report_html = report_html.replace("{{generation_date}}", end_date.strftime("%d de %B de %Y"))

    new_report = {"student_id": student_obj_id, "generated_at": datetime.now(timezone.utc), "html_content": report_html}
    await db["relatorios"].insert_one(new_report)
    logger.info(f"Successfully saved new orchestrated report for student_id: {student_id}")

    return report_html

async def _build_nutrition_section(checkins: list, macro_goals: dict, past_reports: list, base_context_for_llm: str) -> str:
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
    daily_table = _build_daily_nutrition_table(checkins)
    llm_insights = await generate_report_section("nutrition_analysis", base_context_for_llm)
    return f"""{metrics_grid_1}
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

async def _build_sleep_analysis_section(checkins: list, base_context_for_llm: str) -> str:
    daily_table = _build_daily_sleep_table(checkins)
    llm_insights = await generate_report_section("sleep_analysis", base_context_for_llm)
    return f"""{daily_table}
{llm_insights}"""

def _build_daily_sleep_table(checkins: list) -> str:
    rows = []
    for checkin in checkins:
        date = datetime.fromisoformat(checkin.get("checkin_date")).strftime("%d/%m (%a)")
        s = checkin.get("sleep", {})
        status = "Adequado" if s.get('sleep_duration_hours', 0) >= 7 else "Limite inferior"
        status_class = "positive" if status == "Adequado" else "warning"
        rows.append(f"""<tr>
            <td>{date}</td>
            <td>{s.get('sleep_duration_hours', 0):.1f}h</td>
            <td>{s.get('sleep_quality_rating', 0)}/5</td>
            <td>{s.get('sleep_start_time', '--:--')} - {s.get('sleep_end_time', '--:--')}</td>
            <td><span class=\"{status_class}\">{status}</span></td>
        </tr>""")
    table_rows = "\n".join(rows)
    return f"""<table>
        <thead>
            <tr><th>Data</th><th>Duração</th><th>Qualidade</th><th>Horário</th><th>Status</th></tr>
        </thead>
        <tbody>
            {table_rows}
        </tbody>
    </table>"""

async def _build_training_analysis_section(checkins: list, base_context_for_llm: str) -> str:
    training_checkins = [c for c in checkins if c.get('training', {}).get('training_journal')]
    sessions_performed = len(training_checkins)
    total_sessions_expected = 5
    total_sets = _calculate_total_sets(checkins)
    metrics_grid = f"""<div class="metrics-grid">
        <div class="metric-item">
            <div class="metric-label">Sessões Realizadas</div>
            <div class="metric-value">{sessions_performed}/{total_sessions_expected}</div>
            <div class="metric-comparison">Aderência: <span class="positive">{sessions_performed/total_sessions_expected*100:.0f}%</span></div>
        </div>
        <div class="metric-item">
            <div class="metric-label">Volume Semanal</div>
            <div class="metric-value">~{total_sets} séries</div>
            <div class="metric-comparison">Distribuição completa A-E</div>
        </div>
    </div>"""
    training_details_html = _build_training_details(training_checkins)
    llm_insights = await generate_report_section("training_analysis", base_context_for_llm)
    return f"""{metrics_grid}
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

        details.append(f"""<div class="training-detail manter-junto">
            <strong>{training_name} ({date.strftime("%d/%m - %A")})</strong><br>
            <em>Principais exercícios:</em><br>
            {exercises_html}
            <em>Observação:</em> "{observation}"
        </div>""")

    return "\n".join(details)

def _build_score_cards_section(checkins: list, macro_goals: dict) -> str:
    daily_sleep = [c.get('sleep', {}) for c in checkins]
    sleep_hours = [s.get('sleep_duration_hours', 0) for s in daily_sleep if s.get('sleep_duration_hours', 0) > 0]
    avg_sleep_hours = np.mean(sleep_hours) if sleep_hours else 0
    sleep_quality = [s.get('sleep_quality_rating', 0) for s in daily_sleep if s.get('sleep_quality_rating', 0) > 0]
    avg_sleep_quality = np.mean(sleep_quality) if sleep_quality else 0
    days_less_than_6h = sum(1 for s in sleep_hours if s < 6)
    training_checkins = [c for c in checkins if c.get('training', {}).get('training_journal')]
    sessions_performed = len(training_checkins)
    total_sessions_expected = 5
    training_adherence = (sessions_performed / total_sessions_expected) * 100 if total_sessions_expected > 0 else 0
    daily_nutrition = [c.get('nutrition', {}) for c in checkins]
    proteins = [n.get('protein', 0) for n in daily_nutrition if n.get('protein', 0) > 0]
    protein_goal = macro_goals.get('protein', 1)
    avg_proteins = np.mean(proteins) if proteins else 0
    protein_adherence_days = sum(1 for p in proteins if abs(p - protein_goal) <= 10)
    total_nutrition_days = len(proteins)
    rec_score = 0
    rec_status_class = "critical"
    if avg_sleep_hours >= 7 and avg_sleep_quality >= 4 and days_less_than_6h == 0: rec_score = 9; rec_status_class = "positive"
    elif avg_sleep_hours >= 6.5 and avg_sleep_quality >= 3.5 and days_less_than_6h <= 1: rec_score = 7; rec_status_class = "warning"
    else: rec_score = 5; rec_status_class = "critical"
    perf_score = 0
    perf_status_class = "critical"
    if training_adherence >= 100: perf_score = 10; perf_status_class = "positive"
    elif training_adherence >= 80: perf_score = 8; perf_status_class = "warning"
    else: perf_score = 6; perf_status_class = "critical"
    nutri_score = 0
    nutri_status_class = "critical"
    if protein_adherence_days == total_nutrition_days and avg_proteins >= protein_goal * 0.95: nutri_score = 10; nutri_status_class = "positive"
    elif protein_adherence_days >= total_nutrition_days * 0.8: nutri_score = 8; nutri_status_class = "warning"
    else: nutri_score = 6; nutri_status_class = "critical"
    rec_card = f"""<div class="score-card {rec_status_class}">
        <div class="score-label">Recuperação</div>
        <div class="score-value">{rec_score}/10</div>
        <div class="score-detail">Sono: {avg_sleep_hours:.1f}h média<br>Qualidade: {avg_sleep_quality:.1f}/5<br>{days_less_than_6h} dias <6h</div>
    </div>"""
    perf_card = f"""<div class="score-card {perf_status_class}">
        <div class="score-label">Desempenho</div>
        <div class="score-value">{perf_score}/10</div>
        <div class="score-detail">Aderência: {training_adherence:.0f}%<br>{sessions_performed}/{total_sessions_expected} treinos realizados</div>
    </div>"""
    nutri_card = f"""<div class="score-card {nutri_status_class}">
        <div class="score-label">Alimentação</div>
        <div class="score-value">{nutri_score}/10</div>
        <div class="score-detail">Proteína: {avg_proteins:.0f}g média<br>Aderência: {protein_adherence_days}/{total_nutrition_days} dias<br>Meta: {protein_goal}g</div>
    </div>"""
    return f"""{rec_card}
{perf_card}
{nutri_card}"""
