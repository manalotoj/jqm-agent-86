import sys
import os
import asyncio
from unittest.mock import AsyncMock
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from agent_86.domain.models.message import Message
from agent_86.services.chat_model_service import ChatModelService
from agent_86.tools.tool import ToolResult

@pytest.mark.asyncio
async def test_generate_reply_structured_input_with_tool_and_assistant_mock(monkeypatch):
    service = ChatModelService()

    history = [
        Message(id="1", session_id="s1", user_id="u1", role="user", content="Hello, how are you?"),
        Message(id="2", session_id="s1", user_id="u1", role="assistant", content="I am fine, thank you."),
        Message(id="3", session_id="s1", user_id="u1", role="system", content="[tool:web_search] Found info about AI."),
        Message(id="4", session_id="s1", user_id="u1", role="user", content="Can you tell me more about AI based on the info?"),
    ]

    tool_results = [
        ToolResult(tool_name="web_search", content="Some search results")
    ]

    mocked_response_text = "This is a mocked reply."

    # Patch the responses.create method to avoid real API calls and capture the input passed to it
    mock_create = AsyncMock(return_value=type("Response", (), {"output_text": mocked_response_text})())
    monkeypatch.setattr(service._client.responses, "create", mock_create)

    response_text = await service.generate_reply(messages=history, model="gpt-4.1-mini-2", tool_results=tool_results)

    # Verify mocked call was made
    mock_create.assert_called_once()
    call_args = mock_create.call_args.kwargs
    input_payload = call_args.get("input")

    # Assert the input payload has correct role-conditional content types
    assistant_content = next(
        (msg for msg in input_payload if msg["role"] == "assistant"), None
    )
    tool_system_content = next(
        (msg for msg in input_payload if msg["role"] == "system" and msg["content"][0]["text"].startswith("[tool:web_search]")),
        None,
    )
    synthetic_tool_message = next(
        (msg for msg in input_payload if msg["role"] == "system" and msg["content"][0]["text"] == "External tools were executed. Their results are included in the conversation history."),
        None,
    )

    assert assistant_content is not None
    assert tool_system_content is not None
    assert synthetic_tool_message is not None

    # assistant content type should be output_text
    assert assistant_content["content"][0]["type"] == "output_text"

    # system messages content type should be input_text
    assert tool_system_content["content"][0]["type"] == "input_text"
    assert synthetic_tool_message["content"][0]["type"] == "input_text"

    # Output text matches mocked response
    assert response_text == mocked_response_text

if __name__ == "__main__":
    asyncio.run(test_generate_reply_structured_input_with_tool_and_assistant_mock())