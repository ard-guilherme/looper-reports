import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from bson import ObjectId
from datetime import datetime, UTC
from fastapi import HTTPException

from app.services.report_service import create_report_for_student

# Helper to create an awaitable result
def async_return(result):
    f = asyncio.Future()
    f.set_result(result)
    return f

# Realistic mock of a check-in document
SAMPLE_CHECKIN = {
    "_id": ObjectId(),
    "student_id": ObjectId("68d9d0acec34f543218f9059"),
    "checkin_date": "2025-11-01",
    "created_at": datetime.now(UTC),
    "nutrition": { "calories": 2378, "protein": 168, "carbs": 247, "fat": 84 },
    "sleep": { "sleep_start_time": "00:43", "sleep_end_time": "07:38", "sleep_quality_rating": 5, "sleep_duration_hours": 6.9 },
    "training": { "training_journal": "Sexta Feira- Upper\n...\n\nSupino Inclinado Na Máquina\nSérie 1: 45 kg x 12\nSérie 2: 45 kg x 12\n\nPec Deck\nSérie 1: 70 kg x 12\n" }
}

@pytest.mark.asyncio
async def test_create_report_for_student_success():
    """
    Tests the successful creation of a report, verifying the data formatting logic.
    """
    # Arrange
    mock_db = AsyncMock()
    student_id = str(ObjectId())
    student_name = "Test Student"

    mock_db["students"].find_one.return_value = async_return({"_id": ObjectId(student_id), "name": student_name, "additional_context": "Test context"})
    mock_db["checkins"].find.return_value.to_list.return_value = async_return([SAMPLE_CHECKIN])
    mock_db["relatorios"].find.return_value.sort.return_value.limit.return_value.to_list.return_value = async_return([])
    mock_db["relatorios"].insert_one.return_value = async_return(None)

    with patch("app.services.report_service.generate_report_content", new_callable=AsyncMock) as mock_generate_content:
        mock_generate_content.return_value = f"<html>Report for {student_name}</html>"

        # Act
        html_output = await create_report_for_student(student_id, mock_db)

        # Assert
        assert f"<html>Report for {student_name}</html>" in html_output
        
        # Verify the agent was called
        mock_generate_content.assert_called_once()
        
        # Inspect the formatted prompt string passed to the agent
        formatted_prompt = mock_generate_content.call_args[0][0]
        
        # Check main placeholders
        assert f"ALUNO: {student_name}" in formatted_prompt
        assert "CONTEXTO ADICIONAL:\nTest context" in formatted_prompt

        # Check training data formatting
        assert "Supino Inclinado Na Máquina" in formatted_prompt
        assert "Série 1: 45 kg x 12" in formatted_prompt
        
        # Check nutrition data formatting
        assert "01/11/2025: 2378kcal | 168g | 247g | 84g" in formatted_prompt
        
        # Check sleep data formatting
        assert "01/11/2025: 6.9h | Qualidade 5/5 | 00:43-07:38" in formatted_prompt
        
        # Check that the new report was saved
        mock_db["relatorios"].insert_one.assert_called_once()

@pytest.mark.asyncio
async def test_create_report_student_not_found():
    """
    Tests that an HTTPException is raised when the student is not found.
    """
    # Arrange
    mock_db = AsyncMock()
    student_id = str(ObjectId())
    mock_db["students"].find_one.return_value = async_return(None)

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await create_report_for_student(student_id, mock_db)
    
    assert exc_info.value.status_code == 404
