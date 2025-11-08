import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.db.session import get_database
from main import app

# Mock para a dependência do banco de dados
async def override_get_database():
    yield AsyncMock()

app.dependency_overrides[get_database] = override_get_database

client = TestClient(app)

@pytest.mark.asyncio
async def test_generate_report_success():
    """ 
    Tests the successful generation of a report.
    """
    student_id = "60d5ec49f7e4e2a4e8f3b8a2"
    
    # Mock a função do serviço diretamente, já que a dependência do DB já foi mockada
    with patch("app.api.v1.endpoints.reports.create_report_for_student", new_callable=AsyncMock) as mock_create_report:
        mock_create_report.return_value = "<html><body><h1>Generated Report</h1></body></html>"

        response = client.post(f"/api/v1/reports/generate/{student_id}")

        assert response.status_code == 200
        assert "<html><body><h1>Generated Report</h1></body></html>" in response.text
        mock_create_report.assert_called_once()

@pytest.mark.asyncio
async def test_generate_report_not_found():
    """
    Tests the case where the student ID is not found.
    """
    from fastapi import HTTPException
    student_id = "non_existent_id"

    with patch("app.api.v1.endpoints.reports.create_report_for_student", new_callable=AsyncMock) as mock_create_report:
        mock_create_report.side_effect = HTTPException(status_code=404, detail="Student not found")

        response = client.post(f"/api/v1/reports/generate/{student_id}")

        assert response.status_code == 404
        assert "Student not found" in response.json()["detail"]
