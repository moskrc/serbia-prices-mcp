from pathlib import Path

import pytest

from serbia_prices_mcp.source_format import SourceFormatError, source_columns

COLUMNS = [
    "category_id", "category", "name", "brand", "ean", "unit", "store_format", "price_date",
    "regular_price", "unit_price", "promo_price", "promo_start", "promo_end", "vat", "list_type",
]
HEADER = [
    "KATEGORIJA", "NAZIV KATEGORIJE", "Naziv proizvoda", "Robna marka", "Barkod proizvoda", "Jedinica mere",
    "Naziv trgovca - formata", "Datum cenovnika", "Redovna cena", "Cena po jedinici mere", "Snižena cena",
    "Datum početka sniženja", "Datum kraja sniženja", "Stopa PDV", "VRSTA_CENOVNIKA",
]


def write(tmp_path: Path, header: list[str], prefix: str = "") -> Path:
    path = tmp_path / "prices.csv"
    path.write_text(prefix + ";".join(header) + "\n1;x\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("store_format", ["Naziv trgovca - formata", "Naziv trgovca – formata", "Naziv trgovca – format"])
def test_header_spellings_map_to_fields(tmp_path: Path, store_format: str) -> None:
    header = [store_format if h.startswith("Naziv trgovca") else h for h in HEADER]

    assert source_columns(write(tmp_path, header, prefix="﻿")) == COLUMNS


def test_reordered_columns_keep_file_order(tmp_path: Path) -> None:
    assert source_columns(write(tmp_path, list(reversed(HEADER)))) == list(reversed(COLUMNS))


@pytest.mark.parametrize(
    "header",
    [HEADER[:-1], [*HEADER, "Nova kolona"], [*HEADER[:-1], "Tip cenovnika"], [*HEADER[:-1], HEADER[0]]],
)
def test_unexpected_header_is_rejected(tmp_path: Path, header: list[str]) -> None:
    with pytest.raises(SourceFormatError, match="header"):
        source_columns(write(tmp_path, header))


def test_non_utf8_header_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "prices.csv"
    path.write_bytes((";".join(HEADER) + "\n").encode("cp1250"))

    with pytest.raises(SourceFormatError, match="UTF-8"):
        source_columns(path)
