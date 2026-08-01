from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent_86.domain.models.message import Message
from agent_86.services.chat_model_service import ChatModelService
from agent_86.tools.tool import ToolContext, ToolResult


def build_service_with_mocked_responses(*responses):
    service = ChatModelService.__new__(ChatModelService)
    mock_create = AsyncMock(side_effect=list(responses))
    service._client = SimpleNamespace(
        responses=SimpleNamespace(create=mock_create),
    )
    return service, mock_create


@pytest.mark.asyncio
async def test_generate_reply_returns_final_text_without_transcript_for_plain_assistant_reply():
    service, mock_create = build_service_with_mocked_responses(
        SimpleNamespace(output_text="Hello! How can I help?")
    )
    tool_service = SimpleNamespace(execute_tools=AsyncMock(return_value=[]))

    history = [
        Message(
            id="1",
            session_id="s1",
            user_id="u1",
            role="user",
            content="hello",
        ),
    ]

    reply = await service.generate_reply(
        messages=history,
        model="gpt-5.4",
        tool_service=tool_service,
    )

    mock_create.assert_called_once()
    assert reply.assistant_text == "Hello! How can I help?"
    assert reply.transcript_messages == []


@pytest.mark.asyncio
async def test_generate_reply_persists_only_tool_transcript_messages_before_final_reply():
    service, mock_create = build_service_with_mocked_responses(
        SimpleNamespace(
            output_text="",
            output=[
                SimpleNamespace(
                    type="function_call",
                    call_id="call-1",
                    name="web_search",
                    arguments='{"query":"latest ai news"}',
                )
            ],
        ),
        SimpleNamespace(output_text="Here is the latest AI news summary."),
    )

    history = [
        Message(
            id="1",
            session_id="s1",
            user_id="u1",
            role="user",
            content="What is the latest AI news?",
        ),
    ]

    tool_service = SimpleNamespace(
        execute_tools=AsyncMock(
            return_value=[
                ToolResult(tool_name="web_search", content="Search results", metadata={})
            ]
        )
    )

    reply = await service.generate_reply(
        messages=history,
        model="gpt-5.4",
        tool_service=tool_service,
        available_tool_names=["web_search"],
        tool_context=ToolContext(session_id="s1", user_id="u1"),
    )

    assert mock_create.await_count == 2
    assert reply.assistant_text == "Here is the latest AI news summary."
    assert len(reply.transcript_messages) == 2

    tool_call_message, tool_output_message = reply.transcript_messages

    assert tool_call_message.role == "assistant"
    assert tool_call_message.metadata["message_type"] == "function_call"
    assert tool_call_message.metadata["tool_name"] == "web_search"

    assert tool_output_message.role == "tool"
    assert tool_output_message.content == "Search results"
    assert tool_output_message.metadata["message_type"] == "function_call_output"

    assert all(
        message.content != reply.assistant_text
        for message in reply.transcript_messages
    )