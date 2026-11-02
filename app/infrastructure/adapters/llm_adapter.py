import logging
from typing import Iterator, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ...ports.llm import (
    ChatMessageData,
    ChatCompletionResult,
    ChatStreamChunkResult,
    LlmPort,
)
from ..config.settings import settings

logger = logging.getLogger("memora-ai-llm")

ERROR_FALLBACK_MESSAGE = (
    "Dịch vụ AI hiện tại không khả dụng. Vui lòng kiểm tra lại cấu hình hoặc thử lại sau."
)
NO_API_KEY_MESSAGE = (
    "Dịch vụ AI chưa được cấu hình khóa API (OPENAI_API_KEY)."
)


class LlmAdapter(LlmPort):
    """Adapter for LLM completions and streaming using standard OpenAI / ChatOpenAI specs."""

    def __init__(self, openai_key: str = "", openai_base_url: str = ""):
        self._openai_key = openai_key
        self._openai_base_url = openai_base_url

    @property
    def api_key(self) -> str:
        return self._openai_key or settings.openai_api_key

    @property
    def base_url(self) -> str:
        return self._openai_base_url or settings.openai_base_url

    def _to_lc_messages(self, messages: List[ChatMessageData]):
        lc_msgs = []
        for m in messages:
            if m.role == "system":
                lc_msgs.append(SystemMessage(content=m.content))
            elif m.role == "assistant":
                lc_msgs.append(AIMessage(content=m.content))
            else:
                lc_msgs.append(HumanMessage(content=m.content))
        return lc_msgs

    def _create_client(self, model_name: str, temperature: float) -> Optional[ChatOpenAI]:
        if not self.api_key:
            logger.error("Cannot initialize ChatOpenAI: missing API key.")
            return None

        init_kwargs = {
            "model": model_name,
            "api_key": self.api_key,
            "temperature": temperature,
            "max_retries": settings.llm_max_retries,
            "request_timeout": settings.llm_timeout_seconds,
        }
        if self.base_url:
            init_kwargs["base_url"] = self.base_url
        return ChatOpenAI(**init_kwargs)

    def chat_completion(
        self,
        messages: List[ChatMessageData],
        model: str = "",
        temperature: float = 0.7,
    ) -> ChatCompletionResult:
        model_name = model or settings.openai_model or "gpt-4o-mini"
        prompt_tokens = sum(len(m.content.split()) for m in messages)

        if not self.api_key:
            logger.error(NO_API_KEY_MESSAGE)
            completion_tokens = len(NO_API_KEY_MESSAGE.split())
            return ChatCompletionResult(
                content=NO_API_KEY_MESSAGE,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                finish_reason="stop",
            )

        client = self._create_client(model_name, temperature)
        if not client:
            logger.error(f"Failed to create ChatOpenAI client for model '{model_name}'.")
            completion_tokens = len(ERROR_FALLBACK_MESSAGE.split())
            return ChatCompletionResult(
                content=ERROR_FALLBACK_MESSAGE,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                finish_reason="stop",
            )

        try:
            lc_msgs = self._to_lc_messages(messages)
            res = client.invoke(lc_msgs)
            content = str(res.content)
            completion_tokens = len(content.split())
            return ChatCompletionResult(
                content=content,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                finish_reason="stop",
            )
        except Exception as e:
            logger.error(f"LLM invoke failed for model '{model_name}': {e}", exc_info=True)
            completion_tokens = len(ERROR_FALLBACK_MESSAGE.split())
            return ChatCompletionResult(
                content=ERROR_FALLBACK_MESSAGE,
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
        prompt_tokens = sum(len(m.content.split()) for m in messages)

        if not self.api_key:
            logger.error(NO_API_KEY_MESSAGE)
            tokens = NO_API_KEY_MESSAGE.split(" ")
            for i, token in enumerate(tokens):
                delta = token if i == 0 else " " + token
                yield ChatStreamChunkResult(delta_content=delta, is_done=False)
            yield ChatStreamChunkResult(
                delta_content="",
                is_done=True,
                prompt_tokens=prompt_tokens,
                completion_tokens=len(tokens),
                total_tokens=prompt_tokens + len(tokens),
            )
            return

        client = self._create_client(model_name, temperature)
        if not client:
            logger.error(f"Failed to create ChatOpenAI client for model '{model_name}'.")
            tokens = ERROR_FALLBACK_MESSAGE.split(" ")
            for i, token in enumerate(tokens):
                delta = token if i == 0 else " " + token
                yield ChatStreamChunkResult(delta_content=delta, is_done=False)
            yield ChatStreamChunkResult(
                delta_content="",
                is_done=True,
                prompt_tokens=prompt_tokens,
                completion_tokens=len(tokens),
                total_tokens=prompt_tokens + len(tokens),
            )
            return

        yielded_any = False
        total_tokens = 0
        try:
            lc_msgs = self._to_lc_messages(messages)
            for chunk in client.stream(lc_msgs):
                delta = str(chunk.content or "")
                if delta:
                    yielded_any = True
                    total_tokens += len(delta.split())
                    yield ChatStreamChunkResult(delta_content=delta, is_done=False)

            yield ChatStreamChunkResult(
                delta_content="",
                is_done=True,
                prompt_tokens=prompt_tokens,
                completion_tokens=total_tokens,
                total_tokens=prompt_tokens + total_tokens,
            )
        except Exception as e:
            logger.error(f"LLM stream failed for model '{model_name}': {e}", exc_info=True)
            if not yielded_any:
                tokens = ERROR_FALLBACK_MESSAGE.split(" ")
                for i, token in enumerate(tokens):
                    delta = token if i == 0 else " " + token
                    yield ChatStreamChunkResult(delta_content=delta, is_done=False)
                total_tokens = len(tokens)
            yield ChatStreamChunkResult(
                delta_content="",
                is_done=True,
                prompt_tokens=prompt_tokens,
                completion_tokens=total_tokens,
                total_tokens=prompt_tokens + total_tokens,
            )
