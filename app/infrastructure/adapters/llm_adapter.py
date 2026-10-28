from typing import Iterator, List

from ...ports.llm import (
    ChatMessageData,
    ChatCompletionResult,
    ChatStreamChunkResult,
    LlmPort,
)
from ..config.settings import settings


class LlmAdapter(LlmPort):
    """Adapter for LLM completions and streaming using standard OpenAI client/spec."""

    def __init__(self, openai_key: str = "", openai_base_url: str = ""):
        self.openai_key = openai_key or settings.openai_api_key
        self.openai_base_url = openai_base_url or settings.openai_base_url

    def chat_completion(
        self,
        messages: List[ChatMessageData],
        model: str = "",
        temperature: float = 0.7,
    ) -> ChatCompletionResult:
        model_name = model or settings.openai_model or "gpt-4o-mini"
        last_user_msg = ""
        for m in reversed(messages):
            if m.role == "user":
                last_user_msg = m.content
                break

        if self.openai_key:
            try:
                from langchain_openai import ChatOpenAI
                from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

                init_kwargs = {
                    "model": model_name,
                    "api_key": self.openai_key,
                    "temperature": temperature,
                }
                if self.openai_base_url:
                    init_kwargs["base_url"] = self.openai_base_url

                chat = ChatOpenAI(**init_kwargs)
                lc_msgs = []
                for m in messages:
                    if m.role == "system":
                        lc_msgs.append(SystemMessage(content=m.content))
                    elif m.role == "assistant":
                        lc_msgs.append(AIMessage(content=m.content))
                    else:
                        lc_msgs.append(HumanMessage(content=m.content))

                res = chat.invoke(lc_msgs)
                content = str(res.content)
                prompt_tokens = sum(len(m.content.split()) for m in messages)
                completion_tokens = len(content.split())

                return ChatCompletionResult(
                    content=content,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                    finish_reason="stop",
                )
            except Exception:
                pass

        fallback_content = (
            f"Assistant response to: {last_user_msg}" if last_user_msg else "Hello! How can I assist you today?"
        )
        prompt_tokens = sum(len(m.content.split()) for m in messages)
        completion_tokens = len(fallback_content.split())

        return ChatCompletionResult(
            content=fallback_content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            finish_reason="stop",
        )

    def chat_completion_stream(
        self,
        messages: List[ChatMessageData],
        model: str = "",
        temperature: float = 0.7,
    ) -> Iterator[ChatStreamChunkResult]:
        model_name = model or settings.openai_model or "gpt-4o-mini"
        last_user_msg = ""
        for m in reversed(messages):
            if m.role == "user":
                last_user_msg = m.content
                break

        if self.openai_key:
            try:
                from langchain_openai import ChatOpenAI
                from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

                init_kwargs = {
                    "model": model_name,
                    "api_key": self.openai_key,
                    "temperature": temperature,
                }
                if self.openai_base_url:
                    init_kwargs["base_url"] = self.openai_base_url

                chat = ChatOpenAI(**init_kwargs)
                lc_msgs = []
                for m in messages:
                    if m.role == "system":
                        lc_msgs.append(SystemMessage(content=m.content))
                    elif m.role == "assistant":
                        lc_msgs.append(AIMessage(content=m.content))
                    else:
                        lc_msgs.append(HumanMessage(content=m.content))

                prompt_tokens = sum(len(m.content.split()) for m in messages)
                total_tokens = 0

                for chunk in chat.stream(lc_msgs):
                    delta = str(chunk.content)
                    if delta:
                        total_tokens += len(delta.split())
                        yield ChatStreamChunkResult(
                            delta_content=delta,
                            is_done=False,
                        )

                yield ChatStreamChunkResult(
                    delta_content="",
                    is_done=True,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=total_tokens,
                    total_tokens=prompt_tokens + total_tokens,
                )
                return
            except Exception:
                pass

        full_text = (
            f"Assistant response to: {last_user_msg}" if last_user_msg else "Hello! How can I assist you today?"
        )
        tokens = full_text.split(" ")
        prompt_tokens = sum(len(m.content.split()) for m in messages)

        for i, token in enumerate(tokens):
            delta = token if i == 0 else " " + token
            yield ChatStreamChunkResult(
                delta_content=delta,
                is_done=False,
            )

        yield ChatStreamChunkResult(
            delta_content="",
            is_done=True,
            prompt_tokens=prompt_tokens,
            completion_tokens=len(tokens),
            total_tokens=prompt_tokens + len(tokens),
        )
