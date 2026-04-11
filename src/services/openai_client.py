from openai import AsyncOpenAI

_client: AsyncOpenAI | None = None
_chat_model: str = ""
_embedding_model: str = ""


def init_openai(api_key: str, chat_model: str, embedding_model: str):
    global _client, _chat_model, _embedding_model
    _client = AsyncOpenAI(api_key=api_key)
    _chat_model = chat_model
    _embedding_model = embedding_model


async def chat_with_tools(messages: list[dict], tools: list[dict]) -> tuple:
    """Returns (message, usage_dict)"""
    kwargs = {"model": _chat_model, "messages": messages}
    if tools:
        kwargs["tools"] = tools
    response = await _client.chat.completions.create(**kwargs)
    usage = response.usage
    usage_dict = {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
    } if usage else {}
    return response.choices[0].message, usage_dict


async def embed(text: str) -> list[float]:
    response = await _client.embeddings.create(input=text, model=_embedding_model)
    return response.data[0].embedding
