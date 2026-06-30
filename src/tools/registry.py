from collections.abc import Collection

from src.tools.base import ToolDef

_REGISTRY: dict[str, ToolDef] = {}


def tool(
    *,
    name: str,
    description: str,
    parameters: dict,
    feature: str | None = None,
    cost_class: str = "low",
    available_to: Collection[str] = frozenset(),
    rate_limit: str | None = None,
    timeout_s: int = 30,
    parallel_safe: bool = True,
):
    def deco(fn):
        _REGISTRY[name] = ToolDef(
            name=name,
            description=description,
            parameters=parameters,
            feature=feature,
            cost_class=cost_class,
            available_to=set(available_to),
            rate_limit=rate_limit,
            timeout_s=timeout_s,
            parallel_safe=parallel_safe,
            handler=fn,
        )
        return fn

    return deco


def get(name: str) -> ToolDef:
    return _REGISTRY[name]


def filter_for_op(op_name: str, allowed: set[str]) -> list[ToolDef]:
    return [
        t
        for n, t in _REGISTRY.items()
        if n in allowed and (not t.available_to or op_name in t.available_to)
    ]
