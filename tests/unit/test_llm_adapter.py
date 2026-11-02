from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.infrastructure.adapters.llm_adapter import (
    ERROR_FALLBACK_MESSAGE,
    NO_API_KEY_MESSAGE,
    LlmAdapter,
)
from app.ports.llm import ChatMessageData


@pytest.fixture
def sample_messages():
    return [
        ChatMessageData(role="system", content="You are a helpful assistant."),
        ChatMessageData(role="user", content="Explain gRPC in one sentence."),
        ChatMessageData(role="assistant", content="gRPC is a high performance RPC framework."),
        ChatMessageData(role="user", content="What about protobuf?"),
    ]


# =====================================================================
# 1. MESSAGE MAPPING & CLIENT CREATION
# =====================================================================
def test_to_lc_messages_mapping(sample_messages):
    adapter = LlmAdapter(openai_key="test-key")
    lc_msgs = adapter._to_lc_messages(sample_messages)

    assert len(lc_msgs) == 4
    assert isinstance(lc_msgs[0], SystemMessage)
    assert lc_msgs[0].content == "You are a helpful assistant."
    assert isinstance(lc_msgs[1], HumanMessage)
    assert lc_msgs[1].content == "Explain gRPC in one sentence."
    assert isinstance(lc_msgs[2], AIMessage)
    assert lc_msgs[2].content == "gRPC is a high performance RPC framework."
    assert isinstance(lc_msgs[3], HumanMessage)


def test_create_client_with_custom_base_url():
    adapter = LlmAdapter(openai_key="custom-key", openai_base_url="https://custom.endpoint/v1")
    with patch("app.infrastructure.adapters.llm_adapter.ChatOpenAI") as mock_chat_class:
        client = adapter._create_client(model_name="gpt-4o-mini", temperature=0.3)
        assert client is not None
        mock_chat_class.assert_called_once()
        _, kwargs = mock_chat_class.call_args
        assert kwargs["model"] == "gpt-4o-mini"
        assert kwargs["api_key"] == "custom-key"
        assert kwargs["base_url"] == "https://custom.endpoint/v1"
        assert kwargs["temperature"] == 0.3


# =====================================================================
# 2. MISSING API KEY / OFFLINE BEHAVIOR
# =====================================================================
def test_chat_completion_no_api_key(monkeypatch, sample_messages):
    monkeypatch.setattr("app.infrastructure.adapters.llm_adapter.settings.openai_api_key", "")
    adapter = LlmAdapter(openai_key="")

    res = adapter.chat_completion(messages=sample_messages)
    assert res.content == NO_API_KEY_MESSAGE
    assert res.finish_reason == "stop"
    assert res.prompt_tokens > 0
    assert res.completion_tokens > 0
    assert res.total_tokens == res.prompt_tokens + res.completion_tokens


def test_chat_completion_stream_no_api_key(monkeypatch, sample_messages):
    monkeypatch.setattr("app.infrastructure.adapters.llm_adapter.settings.openai_api_key", "")
    adapter = LlmAdapter(openai_key="")

    chunks = list(adapter.chat_completion_stream(messages=sample_messages))
    assert len(chunks) > 1

    content_chunks = [c.delta_content for c in chunks if not c.is_done]
    full_text = "".join(content_chunks)
    assert full_text == NO_API_KEY_MESSAGE

    final_chunk = chunks[-1]
    assert final_chunk.is_done is True
    assert final_chunk.total_tokens > 0


# =====================================================================
# 3. SUCCESSFUL CHAT COMPLETIONS (UNARY & STREAMING)
# =====================================================================
def test_chat_completion_unary_success(sample_messages):
    adapter = LlmAdapter(openai_key="test-key")

    mock_client = MagicMock()
    mock_client.invoke.return_value = AIMessage(content="Protobuf handles binary serialization.")

    with patch.object(adapter, "_create_client", return_value=mock_client):
        res = adapter.chat_completion(messages=sample_messages, model="gpt-4o-mini")

        assert res.content == "Protobuf handles binary serialization."
        assert res.finish_reason == "stop"
        assert res.completion_tokens == len("Protobuf handles binary serialization.".split())
        assert res.total_tokens == res.prompt_tokens + res.completion_tokens
        mock_client.invoke.assert_called_once()


def test_chat_completion_stream_success(sample_messages):
    adapter = LlmAdapter(openai_key="test-key")

    mock_client = MagicMock()
    mock_client.stream.return_value = [
        AIMessage(content="Protobuf"),
        AIMessage(content=" is"),
        AIMessage(content=" fast."),
    ]

    with patch.object(adapter, "_create_client", return_value=mock_client):
        chunks = list(adapter.chat_completion_stream(messages=sample_messages))

        content_chunks = [c.delta_content for c in chunks if not c.is_done]
        assert "".join(content_chunks) == "Protobuf is fast."

        final_chunk = chunks[-1]
        assert final_chunk.is_done is True
        assert final_chunk.completion_tokens == 3
        assert final_chunk.total_tokens == final_chunk.prompt_tokens + 3


# =====================================================================
# 4. ERROR HANDLING & FALLBACK BEHAVIOR
# =====================================================================
def test_chat_completion_unary_exception(sample_messages):
    adapter = LlmAdapter(openai_key="test-key")

    mock_client = MagicMock()
    mock_client.invoke.side_effect = RuntimeError("OpenAI connection timed out")

    with patch.object(adapter, "_create_client", return_value=mock_client):
        res = adapter.chat_completion(messages=sample_messages)

        assert res.content == ERROR_FALLBACK_MESSAGE
        assert res.finish_reason == "stop"
        assert res.completion_tokens == len(ERROR_FALLBACK_MESSAGE.split())


def test_chat_completion_stream_exception(sample_messages):
    adapter = LlmAdapter(openai_key="test-key")

    mock_client = MagicMock()
    mock_client.stream.side_effect = ConnectionError("OpenAI stream interrupted")

    with patch.object(adapter, "_create_client", return_value=mock_client):
        chunks = list(adapter.chat_completion_stream(messages=sample_messages))

        content_chunks = [c.delta_content for c in chunks if not c.is_done]
        assert "".join(content_chunks) == ERROR_FALLBACK_MESSAGE

        final_chunk = chunks[-1]
        assert final_chunk.is_done is True
        assert final_chunk.completion_tokens == len(ERROR_FALLBACK_MESSAGE.split())


def test_create_client_failure_returns_fallback(sample_messages):
    adapter = LlmAdapter(openai_key="test-key")

    with patch.object(adapter, "_create_client", return_value=None):
        unary_res = adapter.chat_completion(messages=sample_messages)
        assert unary_res.content == ERROR_FALLBACK_MESSAGE

        stream_chunks = list(adapter.chat_completion_stream(messages=sample_messages))
        joined = "".join(c.delta_content for c in stream_chunks if not c.is_done)
        assert joined == ERROR_FALLBACK_MESSAGE
