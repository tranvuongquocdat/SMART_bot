from src.agents.base import OpConfig, Operation

_OP_REGISTRY: dict[str, type[Operation]] = {}


def operation(
    *,
    name,
    triggered_by,
    when=None,
    deps_type,
    prompt_key,
    feature,
    memory_scopes=(),
    tools=(),
    timeout_s=30,
    progress_mode="none",
    max_concurrency_per_bot_account=3,
    cache_prefix_hint=None,
):
    def deco(cls):
        cls._op_config = OpConfig(
            name=name,
            triggered_by=list(triggered_by),
            when=when,
            deps_type=deps_type,
            prompt_key=prompt_key,
            feature=feature,
            memory_scopes=list(memory_scopes),
            tools=set(tools),
            timeout_s=timeout_s,
            progress_mode=progress_mode,
            max_concurrency_per_bot_account=max_concurrency_per_bot_account,
            cache_prefix_hint=cache_prefix_hint,
        )
        _OP_REGISTRY[name] = cls
        return cls

    return deco


class OperationRegistry:
    @staticmethod
    def all() -> list[type[Operation]]:
        return list(_OP_REGISTRY.values())

    @staticmethod
    def by_name(name: str) -> type[Operation]:
        return _OP_REGISTRY[name]
