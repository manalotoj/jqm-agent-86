from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent_86.domain.models.message import Message
from agent_86.services.chat_model_service import ChatModelService
from agent_86.tools.tool import ToolContext, ToolResult


class FakeAsyncStream:
    def __init__(self, events):
        self._events = iter(events)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._events)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


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
    first_call_kwargs = mock_create.await_args_list[0].kwargs
    second_call_kwargs = mock_create.await_args_list[1].kwargs
    assert first_call_kwargs["tool_choice"] == "required"
    assert second_call_kwargs["tool_choice"] == "required"
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


@pytest.mark.asyncio
async def test_generate_reply_stream_emits_deltas_and_returns_final_text():
    completed_response = SimpleNamespace(
        output_text="Hello streaming world",
        output=[],
    )
    service, _ = build_service_with_mocked_responses(
        FakeAsyncStream(
            [
                SimpleNamespace(type="response.output_text.delta", delta="Hello "),
                SimpleNamespace(type="response.output_text.delta", delta="streaming world"),
                SimpleNamespace(type="response.completed", response=completed_response),
            ]
        )
    )

    events = []
    history = [
        Message(
            id="1",
            session_id="s1",
            user_id="u1",
            role="user",
            content="hello",
        ),
    ]

    reply = await service.generate_reply_stream(
        messages=history,
        model="gpt-5.4",
        tool_service=SimpleNamespace(execute_tools=AsyncMock(return_value=[])),
        event_callback=events.append,
    )

    assert reply.assistant_text == "Hello streaming world"
    assert reply.transcript_messages == []
    assert [(event.event, event.data) for event in events] == [
        ("delta", {"text": "Hello "}),
        ("delta", {"text": "streaming world"}),
    ]


@pytest.mark.asyncio
async def test_generate_reply_stream_emits_tool_events_and_persists_transcript_messages():
    first_completed_response = SimpleNamespace(
        output_text="",
        output=[
            SimpleNamespace(
                type="function_call",
                call_id="call-1",
                name="web_search",
                arguments='{"query":"latest ai news"}',
            )
        ],
    )
    second_completed_response = SimpleNamespace(
        output_text="Here is the streamed summary.",
        output=[],
    )

    service, mock_create = build_service_with_mocked_responses(
        FakeAsyncStream(
            [
                SimpleNamespace(type="response.completed", response=first_completed_response),
            ]
        ),
        FakeAsyncStream(
            [
                SimpleNamespace(type="response.output_text.delta", delta="Here is the streamed summary."),
                SimpleNamespace(type="response.completed", response=second_completed_response),
            ]
        ),
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
    events = []

    reply = await service.generate_reply_stream(
        messages=history,
        model="gpt-5.4",
        tool_service=tool_service,
        available_tool_names=["web_search"],
        tool_context=ToolContext(session_id="s1", user_id="u1"),
        event_callback=events.append,
    )

    assert mock_create.await_count == 2
    first_call_kwargs = mock_create.await_args_list[0].kwargs
    second_call_kwargs = mock_create.await_args_list[1].kwargs
    assert first_call_kwargs["tool_choice"] == "required"
    assert second_call_kwargs["tool_choice"] == "required"
    assert reply.assistant_text == "Here is the streamed summary."
    assert len(reply.transcript_messages) == 2
    assert [(event.event, event.data) for event in events] == [
        (
            "tool_call",
            {
                "tool_name": "web_search",
                "call_id": "call-1",
                "arguments": {"query": "latest ai news"},
            },
        ),
        (
            "tool_result",
            {
                "tool_name": "web_search",
                "call_id": "call-1",
                "content": "Search results",
            },
        ),
        ("delta", {"text": "Here is the streamed summary."}),
    ]