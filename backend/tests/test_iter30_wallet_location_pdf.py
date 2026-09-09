"""Iteration 30 — wallet PIN + location carry-through + updated receipt wording."""
from services.pdf import _amount_in_words


def test_amount_in_words_rupees_and_paise():
    assert _amount_in_words(15.15) == "Rupees Fifteen and Fifteen Paise Only"
    assert _amount_in_words(101) == "Rupees One Hundred One Only"
    assert _amount_in_words(1234567.89) == (
        "Rupees Twelve Lakh Thirty Four Thousand Five Hundred Sixty Seven and Eighty Nine Paise Only"
    )
