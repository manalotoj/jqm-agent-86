from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent_86.domain.models.message import Message
from agent_86.services.chat_model_service import ChatModelService
from agent_86.services.tool_guardrails import WebSearchGuardrails
from agent_86.services.tool_service import ToolService
from agent_86.tools.tool import ToolContext, ToolResult
from agent_86.tools.tool_registry import ToolRegistry
from agent_86.tools.web_search_tool import WebSearchTool


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


def build_service_with_mocked_responses(*responses, max_tool_roundtrips_per_request=4):
    service = ChatModelService.__new__(ChatModelService)
    mock_create = AsyncMock(side_effect=list(responses))
    service._settings = SimpleNamespace(
        tool_roundtrip_max_per_request=max_tool_roundtrips_per_request,
    )
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
    assert reply.tool_results == []


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
    assert second_call_kwargs["tool_choice"] == "auto"
    assert reply.assistant_text == "Here is the latest AI news summary."
    assert len(reply.transcript_messages) == 2

    tool_call_message, tool_output_message = reply.transcript_messages

    assert tool_call_message.role == "assistant"
    assert tool_call_message.metadata["message_type"] == "function_call"
    assert tool_call_message.metadata["tool_name"] == "web_search"

    assert tool_output_message.role == "tool"
    assert tool_output_message.content == "Search results"
    assert tool_output_message.metadata["message_type"] == "function_call_output"
    assert len(reply.tool_results) == 1
    assert reply.tool_results[0].tool_name == "web_search"

    assert all(
        message.content != reply.assistant_text
        for message in reply.transcript_messages
    )


@pytest.mark.asyncio
async def test_generate_reply_with_enabled_web_search_does_not_force_tool_for_non_current_prompt():
    service, mock_create = build_service_with_mocked_responses(
        SimpleNamespace(output_text="Paris is the capital of France.", output=[])
    )

    history = [
        Message(
            id="1",
            session_id="s1",
            user_id="u1",
            role="user",
            content="What is the capital of France?",
        ),
    ]

    reply = await service.generate_reply(
        messages=history,
        model="gpt-4.1-mini",
        tool_service=SimpleNamespace(execute_tools=AsyncMock(return_value=[])),
        available_tool_names=["web_search"],
        tool_context=ToolContext(session_id="s1", user_id="u1"),
    )

    assert reply.assistant_text == "Paris is the capital of France."
    assert mock_create.await_count == 1
    assert mock_create.await_args.kwargs["tool_choice"] == "auto"


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
    assert reply.tool_results == []
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
    assert second_call_kwargs["tool_choice"] == "auto"
    assert reply.assistant_text == "Here is the streamed summary."
    assert len(reply.transcript_messages) == 2
    assert len(reply.tool_results) == 1
    assert reply.tool_results[0].content == "Search results"
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


@pytest.mark.asyncio
async def test_generate_reply_stream_with_enabled_web_search_does_not_force_tool_for_non_current_prompt():
    completed_response = SimpleNamespace(
        output_text="Paris is the capital of France.",
        output=[],
    )
    service, mock_create = build_service_with_mocked_responses(
        FakeAsyncStream(
            [
                SimpleNamespace(type="response.output_text.delta", delta="Paris is the capital of France."),
                SimpleNamespace(type="response.completed", response=completed_response),
            ]
        )
    )

    history = [
        Message(
            id="1",
            session_id="s1",
            user_id="u1",
            role="user",
            content="What is the capital of France?",
        ),
    ]

    reply = await service.generate_reply_stream(
        messages=history,
        model="gpt-4.1-mini",
        tool_service=SimpleNamespace(execute_tools=AsyncMock(return_value=[])),
        available_tool_names=["web_search"],
        tool_context=ToolContext(session_id="s1", user_id="u1"),
    )

    assert reply.assistant_text == "Paris is the capital of France."
    assert mock_create.await_count == 1
    assert mock_create.await_args.kwargs["tool_choice"] == "auto"


@pytest.mark.asyncio
async def test_generate_reply_blocks_second_web_search_call_in_same_request_and_still_completes():
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
        SimpleNamespace(
            output_text="",
            output=[
                SimpleNamespace(
                    type="function_call",
                    call_id="call-2",
                    name="web_search",
                    arguments='{"query":"latest ai news today"}',
                )
            ],
        ),
        SimpleNamespace(output_text="Here is the final answer without another paid search.", output=[]),
    )

    web_search_service = SimpleNamespace(
        search=AsyncMock(
            return_value=(
                "Search results",
                {"provider": "stub", "query": "latest ai news", "status": "ok"},
            )
        )
    )
    tool_service = ToolService(
        ToolRegistry(tools=[WebSearchTool(web_search_service)]),
        web_search_guardrails=WebSearchGuardrails(max_calls_per_request=1),
    )

    reply = await service.generate_reply(
        messages=[
            Message(
                id="1",
                session_id="s1",
                user_id="u1",
                role="user",
                content="What is the latest AI news?",
            )
        ],
        model="gpt-5.4",
        tool_service=tool_service,
        available_tool_names=["web_search"],
        tool_context=ToolContext(session_id="s1", user_id="u1"),
    )

    assert mock_create.await_count == 3
    assert web_search_service.search.await_count == 1
    assert reply.assistant_text == "Here is the final answer without another paid search."
    assert len(reply.tool_results) == 2
    assert reply.tool_results[0].metadata["status"] == "ok"
    assert reply.tool_results[1].metadata["blocked"] is True
    assert reply.tool_results[1].metadata["reason"] == "request_limit_exceeded"


@pytest.mark.asyncio
async def test_generate_reply_stream_blocks_second_web_search_call_and_keeps_stream_healthy():
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
        output_text="",
        output=[
            SimpleNamespace(
                type="function_call",
                call_id="call-2",
                name="web_search",
                arguments='{"query":"latest ai news today"}',
            )
        ],
    )
    final_completed_response = SimpleNamespace(
        output_text="Done after enforcing guard rails.",
        output=[],
    )
    service, mock_create = build_service_with_mocked_responses(
        FakeAsyncStream([SimpleNamespace(type="response.completed", response=first_completed_response)]),
        FakeAsyncStream([SimpleNamespace(type="response.completed", response=second_completed_response)]),
        FakeAsyncStream(
            [
                SimpleNamespace(type="response.output_text.delta", delta="Done after enforcing guard rails."),
                SimpleNamespace(type="response.completed", response=final_completed_response),
            ]
        ),
    )

    web_search_service = SimpleNamespace(
        search=AsyncMock(
            return_value=(
                "Search results",
                {"provider": "stub", "query": "latest ai news", "status": "ok"},
            )
        )
    )
    tool_service = ToolService(
        ToolRegistry(tools=[WebSearchTool(web_search_service)]),
        web_search_guardrails=WebSearchGuardrails(max_calls_per_request=1),
    )
    events = []

    reply = await service.generate_reply_stream(
        messages=[
            Message(
                id="1",
                session_id="s1",
                user_id="u1",
                role="user",
                content="What is the latest AI news?",
            )
        ],
        model="gpt-5.4",
        tool_service=tool_service,
        available_tool_names=["web_search"],
        tool_context=ToolContext(session_id="s1", user_id="u1"),
        event_callback=events.append,
    )

    assert mock_create.await_count == 3
    assert web_search_service.search.await_count == 1
    assert reply.assistant_text == "Done after enforcing guard rails."
    assert len(reply.tool_results) == 2
    assert reply.tool_results[1].metadata["blocked"] is True
    assert reply.tool_results[1].metadata["reason"] == "request_limit_exceeded"
    assert [(event.event, event.data) for event in events] == [
        (
            "tool_call",
            {"tool_name": "web_search", "call_id": "call-1", "arguments": {"query": "latest ai news"}},
        ),
        (
            "tool_result",
            {"tool_name": "web_search", "call_id": "call-1", "content": "Search results"},
        ),
        (
            "tool_call",
            {"tool_name": "web_search", "call_id": "call-2", "arguments": {"query": "latest ai news today"}},
        ),
        (
            "tool_result",
            {
                "tool_name": "web_search",
                "call_id": "call-2",
                "content": "Web search was skipped because the per-request search limit was reached.",
            },
        ),
        ("delta", {"text": "Done after enforcing guard rails."}),
    ]


@pytest.mark.asyncio
async def test_generate_reply_stops_offering_tools_after_roundtrip_cap_and_forces_final_answer():
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
        SimpleNamespace(output_text="Final answer after capped tool usage.", output=[]),
        max_tool_roundtrips_per_request=1,
    )

    tool_service = SimpleNamespace(
        execute_tools=AsyncMock(
            return_value=[
                ToolResult(tool_name="web_search", content="Search results", metadata={"status": "ok"})
            ]
        )
    )

    reply = await service.generate_reply(
        messages=[
            Message(
                id="1",
                session_id="s1",
                user_id="u1",
                role="user",
                content="What is the latest AI news?",
            )
        ],
        model="gpt-5.4",
        tool_service=tool_service,
        available_tool_names=["web_search"],
        tool_context=ToolContext(session_id="s1", user_id="u1"),
    )

    assert mock_create.await_count == 2
    first_call_kwargs = mock_create.await_args_list[0].kwargs
    second_call_kwargs = mock_create.await_args_list[1].kwargs
    assert first_call_kwargs["tool_choice"] == "required"
    assert second_call_kwargs["tool_choice"] is None
    assert second_call_kwargs["tools"] == []
    assert tool_service.execute_tools.await_count == 1
    assert reply.assistant_text == "Final answer after capped tool usage."
    assert len(reply.transcript_messages) == 2
    assert len(reply.tool_results) == 1
    assert reply.tool_results[0].content == "Search results"


@pytest.mark.asyncio
async def test_generate_reply_stream_stops_offering_tools_after_roundtrip_cap_and_keeps_streaming():
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
    final_completed_response = SimpleNamespace(
        output_text="Final streamed answer after capped tool usage.",
        output=[],
    )
    service, mock_create = build_service_with_mocked_responses(
        FakeAsyncStream([SimpleNamespace(type="response.completed", response=first_completed_response)]),
        FakeAsyncStream(
            [
                SimpleNamespace(
                    type="response.output_text.delta",
                    delta="Final streamed answer after capped tool usage.",
                ),
                SimpleNamespace(type="response.completed", response=final_completed_response),
            ]
        ),
        max_tool_roundtrips_per_request=1,
    )

    tool_service = SimpleNamespace(
        execute_tools=AsyncMock(
            return_value=[
                ToolResult(tool_name="web_search", content="Search results", metadata={"status": "ok"})
            ]
        )
    )
    events = []

    reply = await service.generate_reply_stream(
        messages=[
            Message(
                id="1",
                session_id="s1",
                user_id="u1",
                role="user",
                content="What is the latest AI news?",
            )
        ],
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
    assert second_call_kwargs["tool_choice"] is None
    assert second_call_kwargs["tools"] == []
    assert tool_service.execute_tools.await_count == 1
    assert reply.assistant_text == "Final streamed answer after capped tool usage."
    assert [(event.event, event.data) for event in events] == [
        (
            "tool_call",
            {"tool_name": "web_search", "call_id": "call-1", "arguments": {"query": "latest ai news"}},
        ),
        (
            "tool_result",
            {"tool_name": "web_search", "call_id": "call-1", "content": "Search results"},
        ),
        ("delta", {"text": "Final streamed answer after capped tool usage."}),
    ]


@pytest.mark.asyncio
async def test_web_search_tool_emits_generated_artifact_when_requested():
    web_search_service = SimpleNamespace(
        search=AsyncMock(
            return_value=(
                "Web search provider: stub\nQuery: latest ai news\n\n1. Result title\nURL: https://example.com\nSnippet: Summary",
                {
                    "provider": "stub",
                    "query": "latest ai news",
                    "status": "ok",
                    "result_count": 1,
                },
            )
        )
    )
    tool = WebSearchTool(web_search_service)

    result = await tool.execute(
        query="latest ai news",
        context=ToolContext(
            session_id="s1",
            user_id="u1",
            metadata={"generate_search_artifact": True},
        ),
    )

    assert result.tool_name == "web_search"
    assert result.metadata["session_id"] == "s1"
    assert result.metadata["user_id"] == "u1"
    assert result.metadata["provider"] == "stub"
    assert len(result.metadata["output_artifacts"]) == 1

    artifact = result.metadata["output_artifacts"][0]
    assert artifact["filename"] == "web-search-stub-results.md"
    assert artifact["content_type"] == "text/markdown"
    assert artifact["metadata"] == {
        "label": "Web search results for: latest ai news",
        "tool_name": "web_search",
        "provider": "stub",
        "query": "latest ai news",
        "result_count": 1,
        "status": "ok",
    }
    assert "# Web Search Results" in artifact["content"]
    assert "latest ai news" in artifact["content"]
    assert "```json" in artifact["content"]


@pytest.mark.asyncio
async def test_web_search_tool_does_not_emit_generated_artifact_by_default():
    web_search_service = SimpleNamespace(
        search=AsyncMock(
            return_value=(
                "Stubbed search results",
                {
                    "provider": "stub",
                    "query": "latest ai news",
                    "status": "ok",
                    "result_count": 1,
                },
            )
        )
    )
    tool = WebSearchTool(web_search_service)

    result = await tool.execute(
        query="latest ai news",
        context=ToolContext(session_id="s1", user_id="u1"),
    )

    assert "output_artifacts" not in result.metadata


@pytest.mark.asyncio
async def test_tool_service_blocks_duplicate_web_search_query_without_calling_provider_twice():
    web_search_service = SimpleNamespace(
        search=AsyncMock(
            return_value=(
                "Search results",
                {"provider": "stub", "query": "latest ai news", "status": "ok"},
            )
        )
    )
    tool_service = ToolService(
        ToolRegistry(tools=[WebSearchTool(web_search_service)]),
        web_search_guardrails=WebSearchGuardrails(
            max_calls_per_request=2,
            block_duplicate_queries=True,
        ),
    )
    context = ToolContext(session_id="s1", user_id="u1")

    first_results = await tool_service.execute_tools(
        tool_names=["web_search"],
        query="latest ai news",
        context=context,
    )
    second_results = await tool_service.execute_tools(
        tool_names=["web_search"],
        query="  latest   ai   news  ",
        context=context,
    )

    assert web_search_service.search.await_count == 1
    assert first_results[0].metadata["status"] == "ok"
    assert second_results[0].metadata["blocked"] is True
    assert second_results[0].metadata["reason"] == "duplicate_query"


@pytest.mark.asyncio
async def test_tool_service_blocks_empty_web_search_query_before_provider_call():
    web_search_service = SimpleNamespace(search=AsyncMock())
    tool_service = ToolService(
        ToolRegistry(tools=[WebSearchTool(web_search_service)]),
        web_search_guardrails=WebSearchGuardrails(),
    )

    results = await tool_service.execute_tools(
        tool_names=["web_search"],
        query="   ",
        context=ToolContext(session_id="s1", user_id="u1"),
    )

    web_search_service.search.assert_not_awaited()
    assert results[0].metadata["blocked"] is True
    assert results[0].metadata["reason"] == "empty_query"