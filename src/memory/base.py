from typing import Protocol

from src.domain.memory import Memory, MemoryScope


class MemoryProvider(Protocol):
    async def recall(
        self,
        scope: MemoryScope,
        query: str | None,
        boss_id: int,
        k: int = 5,
    ) -> list[Memory]: ...

    async def write(
        self,
        scope: MemoryScope,
        content: str,
        boss_id: int,
        meta: dict | None = None,
        key: str | None = None,
    ) -> Memory: ...

    async def forget(self, memory_id: int, boss_id: int) -> None: ...
