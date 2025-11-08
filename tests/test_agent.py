import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from app.agents.report_generator_agent import generate_report_content

# Helper to create an awaitable result
def async_return(result):
    f = asyncio.Future()
    f.set_result(result)
    return f

@pytest.mark.asyncio
@patch("app.agents.report_generator_agent.ChatGoogleGenerativeAI")
@patch("app.agents.report_generator_agent.PromptTemplate")
@patch("builtins.open")
@patch("app.agents.report_generator_agent.StrOutputParser")
async def test_generate_report_content(mock_output_parser, mock_open, mock_prompt_template, mock_llm):
    """
    Tests that the agent formats data correctly and invokes the chain.
    """
    # Arrange
    mock_open.return_value.__enter__.return_value.read.return_value = "Prompt content: {user_data_for_prompt}"

    # Mock the final chain instance that will be returned by the chaining operations
    mock_final_chain = AsyncMock()
    mock_final_chain.ainvoke.return_value = "<html>Generated Report</html>"

    # Configure the mocks to return the mock_final_chain when chained
    # This is a bit hacky due to the | operator, but it works.
    # Essentially, we want `prompt | llm | StrOutputParser()` to result in `mock_final_chain`
    # We need to mock the __or__ method of the PromptTemplate instance, then the __or__ of the LLM instance, then the __or__ of the StrOutputParser instance.

    # Mock the result of `prompt | llm`
    mock_prompt_llm_chain = MagicMock()
    mock_prompt_template.return_value.__or__.return_value = mock_prompt_llm_chain

    # Mock the result of `(prompt | llm) | StrOutputParser()`
    mock_prompt_llm_chain.__or__.return_value = mock_final_chain

    user_data_for_prompt = "ALUNO: Test Student\nSEMANA: 1 de Nov 2025"

    # Act
    result = await generate_report_content(user_data_for_prompt)

    # Assert
    assert result == "<html>Generated Report</html>"
    mock_final_chain.ainvoke.assert_called_once_with({"user_data_for_prompt": user_data_for_prompt})


