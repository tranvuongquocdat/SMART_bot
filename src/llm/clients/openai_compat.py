import json
import time

from openai import AsyncOpenAI, OpenAIError

from src.llm.base import ChatMessage, LLMRequest, LLMResponse, LLMUsage, ToolCall


class OpenAICompatibleClient:
    def __init__(self, base_url: str | None, api_key: str):
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = AsyncOpenAI(**kwargs)

    async def chat(self, model: str, req: LLMRequest) -> LLMResponse:
        msgs = [self._to_openai_msg(m) for m in req.messages]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in (req.tools or [])
        ] or None
        t0 = time.time()
        try:
            resp = await self.client.chat.completions.create(
                model=model,
                messages=msgs,
                tools=tools,
                temperature=req.temperature,
                # max_completion_tokens (không phải max_tokens cũ): models OpenAI đời
                # mới (gpt-5.x, o-series) TỪ CHỐI max_tokens. Param mới được cả gpt-4o
                # lẫn Groq chấp nhận → dùng chung an toàn.
                max_completion_tokens=req.max_output_tokens,
            )
        except OpenAIError as e:
            return LLMResponse(
                content=None,
                tool_calls=[],
                status="error",
                error=str(e),
                usage=LLMUsage(0, 0, 0, int((time.time() - t0) * 1000), model, "openai_compat"),
            )
        choice = resp.choices[0].message
        usage = resp.usage
        cached = 0
        details = getattr(usage, "prompt_tokens_details", None)
        if details is not None:
            cached = getattr(details, "cached_tokens", 0) or 0
        return LLMResponse(
            content=choice.content,
            tool_calls=[
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                )
                for tc in (choice.tool_calls or [])
            ],
            usage=LLMUsage(
                tokens_in=usage.prompt_tokens,
                tokens_out=usage.completion_tokens,
                tokens_cached=cached,
                latency_ms=int((time.time() - t0) * 1000),
                model=model,
                provider="openai_compat",
            ),
            status="ok",
        )

    @staticmethod
    def _to_openai_msg(m: ChatMessage) -> dict:
        d: dict = {"role": m.role, "content": m.content}
        if m.role == "tool":
            d["tool_call_id"] = m.tool_call_id
        if m.role == "assistant" and m.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in m.tool_calls
            ]
            if not m.content:
                d["content"] = None
        return d

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        resp = await self.client.embeddings.create(model=model, input=texts)
        return [d.embedding for d in resp.data]
