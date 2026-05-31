import tiktoken

from src.llm.base import LLMRequest
from src.repositories.base import BossContext
from src.repositories.feature_budgets import FeatureBudgetsRepo


def _msg_text(content) -> str:
    return content if isinstance(content, str) else str(content)


def _count_tokens(enc, messages) -> int:
    return sum(len(enc.encode(_msg_text(m.content))) for m in messages)


async def apply_budget(req: LLMRequest, pool) -> LLMRequest:
    repo = FeatureBudgetsRepo(pool, BossContext(boss_id=req.boss_id, user_role="boss"))
    budget = await repo.get(req.feature)
    if not budget:
        return req
    req.max_output_tokens = req.max_output_tokens or budget.max_output_tokens
    try:
        enc = tiktoken.encoding_for_model("gpt-4o-mini")
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")
    total = _count_tokens(enc, req.messages)
    while total > budget.max_input_tokens:
        progressed = False
        for step in budget.trim_policy_json:
            if step == "drop_oldest_delta":
                for i, m in enumerate(req.messages):
                    if m.role == "user" and i > 1:
                        req.messages.pop(i)
                        progressed = True
                        break
            elif step == "drop_low_score_retrieval":
                for i, m in enumerate(req.messages):
                    if m.name == "retrieval":
                        req.messages.pop(i)
                        progressed = True
                        break
            elif step == "truncate_group_note":
                for i, m in enumerate(req.messages):
                    if m.name == "group_note" and isinstance(m.content, str):
                        req.messages[i].content = m.content[: len(m.content) // 2]
                        progressed = True
                        break
            if progressed:
                break
        if not progressed:
            break
        new_total = _count_tokens(enc, req.messages)
        if new_total >= total:
            break
        total = new_total
    return req
