import time

import google.generativeai as genai

from src.llm.base import LLMRequest, LLMResponse, LLMUsage


class GeminiClient:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)

    async def chat(self, model: str, req: LLMRequest) -> LLMResponse:
        sys_msg = next((m.content for m in req.messages if m.role == "system"), None)
        m = genai.GenerativeModel(model, system_instruction=sys_msg)
        contents = [
            {
                "role": "user" if msg.role != "assistant" else "model",
                "parts": [
                    msg.content
                    if isinstance(msg.content, str)
                    else (msg.content[0].get("text", "") if msg.content else "")
                ],
            }
            for msg in req.messages
            if msg.role != "system"
        ]
        t0 = time.time()
        try:
            resp = await m.generate_content_async(
                contents,
                generation_config={
                    "temperature": req.temperature,
                    "max_output_tokens": req.max_output_tokens,
                },
            )
        except Exception as e:
            return LLMResponse(
                content=None,
                tool_calls=[],
                status="error",
                error=str(e),
                usage=LLMUsage(0, 0, 0, int((time.time() - t0) * 1000), model, "gemini"),
            )
        meta = resp.usage_metadata
        return LLMResponse(
            content=resp.text,
            tool_calls=[],
            usage=LLMUsage(
                tokens_in=meta.prompt_token_count,
                tokens_out=meta.candidates_token_count,
                tokens_cached=getattr(meta, "cached_content_token_count", 0) or 0,
                latency_ms=int((time.time() - t0) * 1000),
                model=model,
                provider="gemini",
            ),
            status="ok",
        )

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        raise NotImplementedError("MVP uses OpenAI embed; Gemini embed Phase 1")
