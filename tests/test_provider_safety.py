import pytest
from services import fivesim


def test_invalid_inventory_is_excluded():
    values = fivesim._options({
        "bad": {"cost": 0, "count": 10},
        "empty": {"cost": 2, "count": 0},
        "good": {"cost": 3, "count": 4, "success_rate": 0.9},
    }, "england", "telegram")
    assert values == [("good", 3.0, 4)]


def test_selection_prefers_quality_then_stock(monkeypatch):
    values = fivesim._options({
        "cheap": {"cost": 1, "count": 2, "success_rate": 0.2},
        "better": {"cost": 4, "count": 1, "success_rate": 0.8},
    }, "england", "telegram")
    assert fivesim.choose_operator(values, "england", "telegram")[:1] == ("better",)


def test_any_operator_is_rejected():
    with pytest.raises(fivesim.FiveSimError):
        import asyncio
        asyncio.run(fivesim.FiveSimClient("test-token").buy("england", "any", "telegram"))
