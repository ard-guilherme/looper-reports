import pytest
from unittest.mock import patch, AsyncMock
from app.agents.report_generator_agent import generate_report_content

@pytest.mark.asyncio
@patch("app.agents.report_generator_agent.PromptTemplate")
@patch("app.agents.report_generator_agent.ChatGoogleGenerativeAI")
async def test_generate_report_content(mock_llm, mock_prompt_template):
    """
    Tests that the agent formats data correctly and invokes the chain.
    """
    # Arrange
    # Since we patch the class, the instance will be a MagicMock, not an AsyncMock
    mock_llm_instance = mock_llm.return_value
    mock_prompt_instance = mock_prompt_template.return_value

    # Mock the chaining behavior
    mock_chain_step1 = AsyncMock()
    mock_prompt_instance.__or__.return_value = mock_chain_step1
    mock_chain_step2 = AsyncMock()
    mock_chain_step1.__or__.return_value = mock_chain_step2
    mock_chain_step2.ainvoke.return_value = "Generated Report"

    student_data = {
        "student_profile": {"name": "Test Student"},
        "checkins": [{"date": "2025-11-01"}],
        "macro_goals": [{"protein": 150}],
        "bioimpedance_data": [{"body_fat": 20}],
        "past_reports": [{"content": "Old report"}]
    }

    # Act
    result = await generate_report_content(student_data)

    # Assert
    assert result == "Generated Report"
    mock_chain_step2.ainvoke.assert_called_once()
