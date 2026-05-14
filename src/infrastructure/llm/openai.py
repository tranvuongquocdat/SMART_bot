"""OpenAI implementation of LLMClient.

Each instance owns its own AsyncOpenAI client + model choices. At call
time, sentinels in message content (`[OPENAI_FILE: ...]` /
`[LOCAL_IMAGE: ...]`) are expanded into chat.completions content parts.
Messages without sentinels pass through unchanged.
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from src.infrastructure.llm.base import LLMClient
from src.utils.sentinels import SentinelRef, parse_sentinels

logger = logging.getLogger("llm.openai")


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
        processed = [_inject_file_parts(m) for m in messages]
        call_kwargs: dict[str, Any] = {
            "model": model or self._chat_model,
            "messages": processed,
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


def _inject_file_parts(msg):
    """Replace string content with content-parts list when sentinels present.

    Messages can be either dicts (system/user/tool) OR Pydantic
    ChatCompletionMessage instances (assistant replies appended after a
    tool round). The latter never carry sentinels — pass through.
    """
    if not isinstance(msg, dict):
        return msg
    content = msg.get("content")
    if not isinstance(content, str):
        return msg
    cleaned, refs = parse_sentinels(content)
    if not refs:
        return msg
    parts: list[dict] = []
    if cleaned:
        parts.append({"type": "text", "text": cleaned})
    for ref in refs:
        part = _ref_to_part(ref)
        if part:
            parts.append(part)
    return {**msg, "content": parts}


def _ref_to_part(ref: SentinelRef) -> dict | None:
    if ref.kind == "OPENAI_FILE":
        fid = ref.fields.get("file_id")
        if not fid:
            return None
        return {"type": "file", "file": {"file_id": fid}}
    if ref.kind == "LOCAL_IMAGE":
        path = ref.fields.get("path")
        mime = ref.fields.get("mime", "image/jpeg")
        # OpenAI Vision only accepts these image types — old conversation
        # history may still contain sentinels with stale/wrong mime
        # (octet-stream, heic before conversion was added). Drop those
        # gracefully instead of letting the API call 400.
        if mime not in {"image/jpeg", "image/png", "image/gif", "image/webp"}:
            return {"type": "text", "text": "[Ảnh không đọc được]"}
        if not path or not Path(path).exists():
            return {"type": "text", "text": "[Ảnh đã hết hạn]"}
        try:
            data = Path(path).read_bytes()
        except OSError as e:
            logger.warning("read local image %s failed: %s", path, e)
            return {"type": "text", "text": "[Ảnh đã hết hạn]"}
        b64 = base64.b64encode(data).decode("ascii")
        return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
    return None
