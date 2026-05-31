from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass
class Hit:
    message_id: int
    score: float
    text: str
    sender: str | None
    ts: str
    source: str


@dataclass
class RetrievalContext:
    boss_id: int
    chat_id: str | None = None
    days: int | None = None


class RetrievalStage(Protocol):
    name: str
    kind: Literal["source", "combinator", "fuser", "dedupe", "reranker"]

    async def run(
        self, query: str, hits: "list[Hit]", ctx: RetrievalContext
    ) -> "list[Hit]": ...


_REGISTRY: dict[str, type] = {}


def retrieval_stage(name: str, kind: str):
    def deco(cls):
        cls.name = name
        cls.kind = kind
        _REGISTRY[name] = cls
        return cls

    return deco


def get_stage_class(name: str):
    return _REGISTRY[name]
