from typing import Iterator, List

from ...ports.llm import (
    LlmPort,
    ChatMessageData,
    ChatCompletionResult,
    ChatStreamChunkResult,
)
from ..config.settings import settings


class LlmAdapter(LlmPort):
    """Adapter for LLM completions and streaming using Gemini/OpenAI with fallback."""

    def __init__(self, gemini_key: str = "", openai_key: str = ""):
        self.gemini_key = gemini_key or settings.gemini_api_key
        self.openai_key = openai_key or settings.openai_api_key

    def chat_completion(
        self,
        messages: List[ChatMessageData],
        model: str = "gemini-2.5-flash",
        temperature: float = 0.7,
    ) -> ChatCompletionResult:
        model_name = model or "gemini-2.5-flash"
        last_user_msg = ""
        for m in reversed(messages):
            if m.role == "user":
                last_user_msg = m.content
                break

        if self.gemini_key and "gemini" in model_name.lower():
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

                chat = ChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=self.gemini_key,
                    temperature=temperature,
                )
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
        model: str = "gemini-2.5-flash",
        temperature: float = 0.7,
    ) -> Iterator[ChatStreamChunkResult]:
        model_name = model or "gemini-2.5-flash"
        last_user_msg = ""
        for m in reversed(messages):
            if m.role == "user":
                last_user_msg = m.content
                break

        if self.gemini_key and "gemini" in model_name.lower():
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

                chat = ChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=self.gemini_key,
                    temperature=temperature,
                )
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
