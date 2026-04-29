"""OpenAI implementation of LLMClient.

Each instance owns its own AsyncOpenAI client + model choices, so per-boss
credentials work without touching globals. Phase 4b services construct one
of these per request via `factory.get_llm_client(boss, settings)`.
"""
from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from src.infrastructure.llm.base import LLMClient


class OpenAILLMClient(LLMClient):
    def __init__(
        self,
        api_key: str,
        chat_model: str,
        embedding_model: str,
        embedding_dim: int,
    ) -> None:
        self._api_key = api_key
        self._chat_model = chat_model
        self._embedding_model = embedding_model
        self._embedding_dim = embedding_dim
        self._client = AsyncOpenAI(api_key=api_key)

    @property
    def chat_model(self) -> str:
        return self._chat_model

    @property
    def embedding_model(self) -> str:
        return self._embedding_model

    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> tuple[Any, dict]:
        """Returns (message, usage_dict). Same shape as legacy openai_client."""
        call_kwargs: dict[str, Any] = {
            "model": model or self._chat_model,
            "messages": messages,
            **kwargs,
        }
        if tools:
            call_kwargs["tools"] = tools
        response = await self._client.chat.completions.create(**call_kwargs)
        usage = response.usage
        usage_dict = {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
        } if usage else {}
        return response.choices[0].message, usage_dict

    async def embed(self, text: str) -> tuple[list[float], int]:
        response = await self._client.embeddings.create(
            input=text, model=self._embedding_model,
        )
        return response.data[0].embedding, self._embedding_dim
