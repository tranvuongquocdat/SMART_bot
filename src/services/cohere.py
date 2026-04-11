import httpx

_client: httpx.AsyncClient | None = None
_api_key: str = ""


async def init_cohere(api_key: str):
    global _client, _api_key
    _api_key = api_key
    _client = httpx.AsyncClient(timeout=30.0)


async def rerank(query: str, documents: list[str], top_n: int = 5) -> list[int]:
    if len(documents) <= top_n:
        return list(range(len(documents)))

    resp = await _client.post(
        "https://api.cohere.com/v2/rerank",
        headers={"Authorization": f"Bearer {_api_key}"},
        json={
            "model": "rerank-v3.5",
            "query": query,
            "documents": documents,
            "top_n": top_n,
        },
    )
    resp.raise_for_status()
    return [r["index"] for r in resp.json()["results"]]


async def close_cohere():
    if _client:
        await _client.aclose()
