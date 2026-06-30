import time

from src.domain.model import Model
from src.repositories.base import BossContext
from src.repositories.models import ModelsRepo


class ModelRegistry:
    """Cache models DB (TTL 60s + invalidate on registry.invalidated event)."""

    def __init__(self, pool, bus):
        self._pool = pool
        self._bus = bus
        self._cache: dict[int, Model] = {}
        self._loaded_at = 0.0
        bus.subscribe("registry.invalidated", self._handle_invalidate)

    async def _handle_invalidate(self, payload):
        if payload.get("registry_name") == "models":
            self._loaded_at = 0.0

    async def _ensure_loaded(self):
        if time.time() - self._loaded_at < 60 and self._cache:
            return
        repo = ModelsRepo(self._pool, BossContext(boss_id=0, user_role="superadmin"))
        all_models = await repo.list_all(active_only=True)
        self._cache = {m.id: m for m in all_models}
        self._loaded_at = time.time()

    async def get(self, model_id: int) -> Model:
        await self._ensure_loaded()
        if model_id not in self._cache:
            # Refresh once before failing (model may have been just added).
            self._loaded_at = 0.0
            await self._ensure_loaded()
        return self._cache[model_id]

    async def platform_default(self, tier: str) -> Model:
        await self._ensure_loaded()
        for m in self._cache.values():
            if m.tier == tier and m.is_platform_default and m.is_active:
                return m
        raise LookupError(f"no platform default for tier={tier}")
