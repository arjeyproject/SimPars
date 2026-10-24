import asyncio
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
        asyncio.run(fivesim.FiveSimClient("test-token").buy("england", "any", "telegram"))


def test_country_options_falls_back_to_full_catalog(monkeypatch):
    from services import availability

    async def empty_options(product, use_cache=True):
        return {}

    async def empty_prices(product, use_cache=True):
        return {}

    async def empty_request(path):
        return {}

    async def country_product_catalog(use_cache=True):
        # The 5SIM response can be normalized as product -> country -> option.
        return {"telegram": {"england": ("vodafone", 3.0, 4)}}

    monkeypatch.setattr(fivesim, "_options_cache", {})
    monkeypatch.setattr(fivesim, "get_product_options", empty_options)
    monkeypatch.setattr(fivesim, "get_product_prices", empty_prices)
    monkeypatch.setattr(fivesim, "_request", empty_request)
    monkeypatch.setattr(fivesim, "get_all_prices", country_product_catalog)

    assert asyncio.run(availability.country_options("telegram", "England")) == [("vodafone", 3.0, 4)]


def test_paid_purchase_unavailable_inventory_credits_wallet(monkeypatch):
    from services import purchase_checkout

    credited = []

    async def unavailable(payload):
        raise fivesim.FiveSimError("no free phones")

    async def add_balance(user_id, amount):
        credited.append((user_id, amount))

    monkeypatch.setattr(purchase_checkout, "resolve", unavailable)
    monkeypatch.setattr(purchase_checkout.db, "add_balance", add_balance)

    result = asyncio.run(purchase_checkout.finish_paid_purchase(
        None,
        {"user_id": 77, "amount": 1234},
        {"product": "telegram", "country": "england"},
        "test-ref",
    ))

    assert result[0] is False
    assert result[2] is None
    assert credited == [(77, 1234)]
    assert "کیف پولت برگشت خورد" in result[1]
