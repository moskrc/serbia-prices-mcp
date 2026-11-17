import pytest

from serbia_prices_mcp.normalize import normalize_text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("  Pileći   FILE ", "pileci file"),
        ("ĐUVEČ", "djuvec"),
        ("Žuta ČOKOLADA, ŠEĆER", "zuta cokolada, secer"),
        ("Ценовник ЂУРЂЕВАЧА Љубичица Њива Џем", "cenovnik djurdjevaca ljubicica njiva dzem"),
        (" Кajmak namaz", "kajmak namaz"),
        (None, ""),
    ],
)
def test_serbian_latin_is_folded_to_ascii(text: str | None, expected: str) -> None:
    assert normalize_text(text) == expected
