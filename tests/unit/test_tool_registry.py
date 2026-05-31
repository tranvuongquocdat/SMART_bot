from src.tools.registry import filter_for_op, tool


def test_register_and_filter():
    @tool(
        name="hello",
        description="say hi",
        parameters={"type": "object", "properties": {}},
        available_to={"dm_responder"},
    )
    async def _(ctx):
        return None

    fs = filter_for_op("dm_responder", allowed={"hello"})
    assert len(fs) == 1 and fs[0].name == "hello"
    assert filter_for_op("other_op", allowed={"hello"}) == []
