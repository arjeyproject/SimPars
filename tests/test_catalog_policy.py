from services.sintel_catalog import SERVICE_CATEGORIES, _subcategory


def test_unverified_telegram_subscription_categories_are_not_exposed():
    categories = SERVICE_CATEGORIES["telegram"]["subcategories"]
    assert "premium" not in categories
    assert "stars" not in categories


def test_unknown_provider_service_is_not_mapped_to_sellable_category():
    assert _subcategory("telegram", "generic social package", "") == "other"
