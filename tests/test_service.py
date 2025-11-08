import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from bson import ObjectId
from datetime import datetime, UTC
from fastapi import HTTPException

from app.services.report_service import create_report_for_student

# Helper to create an awaitable result
def async_return(result):
    f = asyncio.Future()
    f.set_result(result)
    return f

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
    "training": { "training_journal": "Supino Reto\nSérie 1: 100 kg x 5" }
}

SAMPLE_MACRO_GOALS = {
    "_id": ObjectId(),
    "student_id": STUDENT_ID,
    "protein": 200
}

STUDENT_DATA = {"_id": STUDENT_ID, "name": STUDENT_NAME, "additional_context": "Test context"}

@pytest.mark.asyncio
async def test_create_report_for_student_success():
    """
    Tests the successful creation of a report, verifying the data analysis and formatting.
    """
    # Arrange
    mock_db = MagicMock()

    # Pre-create the mock for the 'relatorios' collection to ensure the same object is used
    mock_relatorios_collection = MagicMock(
        find=MagicMock(return_value=MagicMock(sort=MagicMock(return_value=MagicMock(limit=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[]))))))),
        insert_one=AsyncMock(return_value=None)
    )

    mock_db.__getitem__.side_effect = lambda collection_name: {
        "students": MagicMock(find_one=AsyncMock(return_value=STUDENT_DATA)),
        "checkins": MagicMock(find=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[SAMPLE_CHECKIN])))),
        "macro_goals": MagicMock(find_one=AsyncMock(return_value=SAMPLE_MACRO_GOALS)),
        "relatorios": mock_relatorios_collection
    }[collection_name]

    with patch("app.services.report_service.generate_report_content", new_callable=AsyncMock) as mock_generate_content:
        mock_generate_content.return_value = f"<html>Report for {STUDENT_NAME}</html>"

        # Act
        html_output = await create_report_for_student(str(STUDENT_ID), mock_db)

        # Assert
        assert f"<html>Report for {STUDENT_NAME}</html>" in html_output
        mock_generate_content.assert_called_once()
        
        formatted_prompt = mock_generate_content.call_args[0][0]
        
        assert f"ALUNO: {STUDENT_NAME}" in formatted_prompt
        assert "Supino Reto" in formatted_prompt
        assert "2500kcal | 180g" in formatted_prompt
        assert "8.0h | Qualidade 5/5" in formatted_prompt

        assert "RESUMO NUTRICIONAL" in formatted_prompt
        assert "Calorias Médias: 2500 kcal" in formatted_prompt
        assert "Proteína Média: 180g (Meta: 200g, Aderência: 90%)" in formatted_prompt
        assert "Coeficiente de Variação (Calorias): 0.0%" in formatted_prompt
        assert "Média de Sono: 8.0 horas/noite" in formatted_prompt
        assert "Volume Total (Séries): 1 séries" in formatted_prompt

        mock_relatorios_collection.insert_one.assert_called_once()

@pytest.mark.asyncio
async def test_create_report_student_not_found():
    """
    Tests that an HTTPException is raised when the student is not found.
    """
    # Arrange
    mock_db = MagicMock()
    mock_db["students"].find_one.return_value = async_return(None)

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await create_report_for_student(str(ObjectId()), mock_db)
    
    assert exc_info.value.status_code == 404