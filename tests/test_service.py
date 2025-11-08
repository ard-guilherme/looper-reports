import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from bson import ObjectId
from fastapi import HTTPException

from app.services.report_service import create_report_for_student

# Helper to create an awaitable result
def async_return(result):
    f = asyncio.Future()
    f.set_result(result)
    return f

@pytest.mark.asyncio
async def test_create_report_for_student_success():
    """
    Tests the successful creation of a report in the service layer.
    """
    # Arrange
    mock_db = AsyncMock()
    student_id = str(ObjectId())

    # Mock the database find_one and find calls to return awaitable results
    mock_db["students"].find_one.return_value = async_return({"_id": ObjectId(student_id), "name": "Test Student"})
    mock_db["checkins"].find.return_value.to_list.return_value = async_return([])
    mock_db["macro_goals"].find.return_value.to_list.return_value = async_return([])
    mock_db["bioimpedancias"].find.return_value.to_list.return_value = async_return([])
    mock_db["relatorios"].find.return_value.sort.return_value.limit.return_value.to_list.return_value = async_return([])
    mock_db["relatorios"].insert_one.return_value = async_return(None) # Mock insert_one

    with patch("app.services.report_service.generate_report_content", new_callable=AsyncMock) as mock_generate_content:
        mock_generate_content.return_value = "<html>Generated Report</html>"

        # Act
        html_output = await create_report_for_student(student_id, mock_db)

        # Assert
        assert "<html>Generated Report</html>" in html_output
        # O nome do aluno não estará no HTML mockado, pois o mock do agent retorna um HTML genérico.
        # assert "Test Student" in html_output 
        mock_generate_content.assert_called_once()
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
