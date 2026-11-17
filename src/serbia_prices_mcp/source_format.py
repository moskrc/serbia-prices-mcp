from pathlib import Path

from serbia_prices_mcp.normalize import normalize_text


class SourceFormatError(Exception):
    pass


SOURCE_COLUMNS: dict[str, str] = {
    "kategorija": "category_id",
    "naziv kategorije": "category",
    "naziv proizvoda": "name",
    "robna marka": "brand",
    "barkod proizvoda": "ean",
    "jedinica mere": "unit",
    "naziv trgovca - formata": "store_format",
    "naziv trgovca - format": "store_format",
    "datum cenovnika": "price_date",
    "redovna cena": "regular_price",
    "cena po jedinici mere": "unit_price",
    "snizena cena": "promo_price",
    "datum pocetka snizenja": "promo_start",
    "datum kraja snizenja": "promo_end",
    "stopa pdv": "vat",
    "vrsta_cenovnika": "list_type",
}


def source_columns(path: Path) -> list[str]:
    try:
        with path.open(encoding="utf-8-sig") as file:
            header = file.readline().rstrip("\r\n").split(";")
    except UnicodeDecodeError as exc:
        raise SourceFormatError(f"CSV is not UTF-8: {exc}") from exc
    columns = [SOURCE_COLUMNS.get(normalize_text(h.strip('"')).replace("–", "-"), "") for h in header]
    if sorted(columns) != sorted(set(SOURCE_COLUMNS.values())):
        raise SourceFormatError(f"unexpected CSV header: {header}")
    return columns
