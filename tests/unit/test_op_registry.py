from dataclasses import dataclass

from src.agents import registry as op_reg
from src.agents.registry import OperationRegistry, operation


@dataclass
class _Deps:
    pass


def test_operation_decorator_registers_and_lookup():
    snap = dict(op_reg._OP_REGISTRY)
    op_reg._OP_REGISTRY.clear()
    try:

        @operation(
            name="t_op",
            triggered_by=["evt.foo"],
            deps_type=_Deps,
            prompt_key="p.t_op",
            feature="responder",
            tools=("tool_a",),
        )
        class TOp:
            async def handle(self, event, ctx):
                return "ok"

        assert TOp._op_config.name == "t_op"
        assert TOp._op_config.triggered_by == ["evt.foo"]
        assert TOp._op_config.tools == {"tool_a"}
        assert OperationRegistry.by_name("t_op") is TOp
        assert TOp in OperationRegistry.all()
    finally:
        op_reg._OP_REGISTRY.clear()
        op_reg._OP_REGISTRY.update(snap)


def test_when_predicate_default_none():
    snap = dict(op_reg._OP_REGISTRY)
    op_reg._OP_REGISTRY.clear()
    try:

        @operation(
            name="t_op2",
            triggered_by=["evt.bar"],
            deps_type=_Deps,
            prompt_key="p.t_op2",
            feature="responder",
        )
        class TOp2:
            async def handle(self, event, ctx):
                return None

        assert TOp2._op_config.when is None
        assert TOp2._op_config.memory_scopes == []
    finally:
        op_reg._OP_REGISTRY.clear()
        op_reg._OP_REGISTRY.update(snap)
