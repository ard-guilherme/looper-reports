import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from bson import ObjectId
from datetime import datetime, UTC
from fastapi import HTTPException

from app.services.report_service import create_report_for_student
from app.core.config import settings

# Mocks for database documents
STUDENT_ID = ObjectId()
STUDENT_NAME = "Test Student"

SAMPLE_CHECKIN = {
    "_id": ObjectId(),
    "student_id": STUDENT_ID,
    "checkin_date": "2025-11-01",
    "created_at": datetime.now(UTC),
    "nutrition": { "calories": 2500, "protein": 180, "carbs": 250, "fat": 90 },
    "sleep": { "sleep_duration_hours": 8.0, "sleep_quality_rating": 5, "sleep_start_time": "23:00", "sleep_end_time": "07:00" },
    "training": { "training_journal": "Supino Reto\nSérie 1: 100 kg x 5", "student_observation": "Me senti forte hoje."
}
}

SAMPLE_MACRO_GOALS = {
    "_id": ObjectId(),
    "student_id": STUDENT_ID,
    "protein": 200
}

STUDENT_DATA = {"_id": STUDENT_ID, "name": STUDENT_NAME, "additional_context": "Test context"}

IDEAL_TEMPLATE_CONTENT = """<!DOCTYPE html>
<html>
<head><title>Relatório</title></head>
<body>
    <h1>Relatório para {{student_name}}</h1>
    <p>Semana: {{week_string}}</p>
    <div id=\"overview\">{{overview_section}}</div>
    <div id=\"scores\">{{score_cards}}</div>
    <div id=\"nutrition\">{{nutrition_analysis_section}}</div>
    <div id=\"sleep\">{{sleep_analysis_section}}</div>
    <div id=\"training\">{{training_analysis_section}}</div>
    <div id=\"insights\">{{detailed_insights_section}}</div>
    <div id=\"recs\">{{recommendations_section}}</div>
    <div id=\"conclusion\">{{conclusion_section}}</div>
    <p>Próxima semana: {{next_week_string}}</p>
    <p>Gerado em: {{generation_date}}</p>
</body>
</html>"""

@pytest.fixture(autouse=True)
def override_settings(monkeypatch):
    monkeypatch.setattr(settings, 'REPORT_TEMPLATE_FILE', 'mock_template.html')

@pytest.mark.asyncio
async def test_create_report_orchestration_flow():
    """
    Tests the new orchestration flow, ensuring the correct agent is called
    and the template is populated.
    """
    # Arrange
    mock_db = MagicMock()
    mock_relatorios_collection = MagicMock(
        insert_one=AsyncMock(return_value=None),
        find=MagicMock(return_value=MagicMock(
            sort=MagicMock(return_value=MagicMock(
                limit=MagicMock(return_value=MagicMock(
                    to_list=AsyncMock(return_value=[])  # Return an empty list for past reports
                ))
            ))
        ))
    )

    mock_db.__getitem__.side_effect = lambda collection_name: {
        "students": MagicMock(find_one=AsyncMock(return_value=STUDENT_DATA)),
        "checkins": MagicMock(find=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[SAMPLE_CHECKIN])))),
        "macro_goals": MagicMock(find_one=AsyncMock(return_value=SAMPLE_MACRO_GOALS)),
        "relatorios": mock_relatorios_collection
    }[collection_name]

    # Mock the file system read for the template
    with patch("builtins.open", new_callable=MagicMock) as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = IDEAL_TEMPLATE_CONTENT
        
        # Mock the specialist agent to return different content based on the section
        async def side_effect(section_type, context_data):
            if section_type == "overview":
                return "Este é o resumo da visão geral gerado pelo LLM."
            elif section_type == "nutrition_analysis":
                return "<p>Insights de nutrição gerados pelo LLM.</p>"
            elif section_type == "sleep_analysis":
                return "<p>Insights de sono gerados pelo LLM.</p>"
            elif section_type == "training_analysis":
                return "<p>Insights de treino gerados pelo LLM.</p>"
            return ""
        
        with patch("app.services.report_service.generate_report_section", new_callable=AsyncMock) as mock_generate_section:
            mock_generate_section.side_effect = side_effect

            # Act
            final_html = await create_report_for_student(str(STUDENT_ID), mock_db)

            # Assert
            # 1. Check that the correct agents were called
            assert mock_generate_section.call_count == 4
            assert mock_generate_section.call_args_list[0].args[0] == "overview"
            assert mock_generate_section.call_args_list[1].args[0] == "nutrition_analysis"
            assert mock_generate_section.call_args_list[2].args[0] == "sleep_analysis"
            assert mock_generate_section.call_args_list[3].args[0] == "training_analysis"

            # 2. Check that the template was populated correctly
            assert "<p>Insights de treino gerados pelo LLM.</p>" in final_html
            
            # 3. Check for structural elements from the training section
            assert '<div class="training-detail manter-junto">' in final_html
            assert "<em>Observação:</em> \"Me senti forte hoje.\"" in final_html

            # 4. Check for structural elements from the score cards section
            assert '<div class="score-card positive">' in final_html
            assert '<div class="score-label">Recuperação</div>' in final_html
            assert '<div class="score-value">9/10</div>' in final_html

            # 5. Check that other sections are placeholder comments
            assert "<!-- Detailed insights to be implemented -->" in final_html
            
            # 6. Check that the report was saved
            mock_relatorios_collection.insert_one.assert_called_once()