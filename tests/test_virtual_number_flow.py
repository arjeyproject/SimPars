from keyboards import countries_kb
from utils import country_title


def test_country_row_has_three_aligned_actions_with_same_callback():
    markup = countries_kb("telegram", [("🇬🇧 انگلیس", "۲٬۴۰۰ تومان", "cn:telegram:england:economic")])
    row = markup.inline_keyboard[0]
    assert len(row) == 3
    assert [button.callback_data for button in row] == ["cn:telegram:england:economic"] * 3
    assert row[0].text.startswith("🟩")
    assert row[1].text.startswith("🟦")
    assert row[2].text.startswith("🟧")


def test_country_title_uses_persian_name_when_known():
    assert country_title("england", {"england": {"iso": {"GB": "United Kingdom"}}}) == "🇬🇧 انگلیس"
