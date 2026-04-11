from openai import AsyncOpenAI

_client: AsyncOpenAI | None = None
_chat_model: str = ""
_embedding_model: str = ""


def init_openai(api_key: str, chat_model: str, embedding_model: str):
    global _client, _chat_model, _embedding_model
    _client = AsyncOpenAI(api_key=api_key)
    _chat_model = chat_model
    _embedding_model = embedding_model


async def chat_with_tools(messages: list[dict], tools: list[dict]) -> dict:
    kwargs = {"model": _chat_model, "messages": messages}
    if tools:
        kwargs["tools"] = tools
    response = await _client.chat.completions.create(**kwargs)
    return response.choices[0].message


async def embed(text: str) -> list[float]:
    response = await _client.embeddings.create(input=text, model=_embedding_model)
    return response.data[0].embedding
