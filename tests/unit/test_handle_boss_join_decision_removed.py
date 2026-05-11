"""handle_boss_join_decision is dead code (regex parser) and must be removed."""
import src.onboarding as onboarding


def test_handle_boss_join_decision_attribute_gone():
    assert not hasattr(onboarding, "handle_boss_join_decision"), (
        "handle_boss_join_decision must be removed; "
        "approval flow is handled by the LLM tools (see spec §2.3)."
    )
