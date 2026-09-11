import pytest

from investment_agent.harness import Budget, BudgetExceeded


def test_child_charge_propagates_to_parent() -> None:
    parent = Budget(max_tokens=1_000, max_usd=1.0)
    child = parent.child(token_fraction=0.5, usd_fraction=0.5)

    child.charge(tokens=100, usd=0.10)

    assert child.used_tokens == 100
    assert parent.used_tokens == 100
    assert parent.used_usd == pytest.approx(0.10)


def test_budget_rejects_charge_before_mutation() -> None:
    budget = Budget(max_tokens=10, max_usd=0.10)

    with pytest.raises(BudgetExceeded):
        budget.charge(tokens=11, usd=0.01)

    assert budget.used_tokens == 0
    assert budget.used_usd == 0

