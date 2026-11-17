import csv
import datetime as dt
import gzip
import re
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Literal, NamedTuple, TextIO

from serbia_prices_mcp.normalize import normalize_text

Unit = Literal["kg", "g", "l", "ml", "m", "cm", "piece", "pack", "roll", "wash", "sheet", "set", "box", "sack", "pair"]


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

SOURCE_UNITS: dict[str, tuple[Unit, int]] = {
    "kg": ("kg", 1), "1kg": ("kg", 1), "kgr": ("kg", 1), "kgm": ("kg", 1), "kg.": ("kg", 1),
    "g": ("g", 1), "gr": ("g", 1), "1g": ("g", 1), "10g": ("g", 10), "100g": ("g", 100), "1000g": ("g", 1000),
    "l": ("l", 1), "lit": ("l", 1), "1l": ("l", 1), "hl": ("l", 1), "1kg/l": ("l", 1),
    "ml": ("ml", 1), "1ml": ("ml", 1), "10ml": ("ml", 10), "30ml": ("ml", 30), "50ml": ("ml", 50),
    "100ml": ("ml", 100), "1000ml": ("ml", 1000),
    "m": ("m", 1), "1m": ("m", 1), "met": ("m", 1),
    "centimetar": ("cm", 1),
    "kom": ("piece", 1), "kom.": ("piece", 1), "komad": ("piece", 1), "ko": ("piece", 1), "jed": ("piece", 1),
    "1kom": ("piece", 1), "12kom": ("piece", 12), "100kom": ("piece", 100), "km": ("piece", 1), "kmd": ("piece", 1),
    "kon": ("piece", 1), "vek": ("piece", 1), "1": ("piece", 1),
    "pak": ("pack", 1), "kor": ("pack", 1), "om": ("pack", 1), "kob": ("pack", 1),
    "set": ("set", 1), "kpl": ("set", 1),
    "kut": ("box", 1),
    "dzak": ("sack", 1),
    "par": ("pair", 1),
    "rln": ("roll", 1),
    "br.pranja": ("wash", 1),
    "listić": ("sheet", 1),
}

LIST_TYPES = {"VAZECI_CENOVNIK": True, "MESECNI_PRESEK": False}

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")

DATE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")


class SourceRow(NamedTuple):
    store_format: str
    ean: str | None
    product_key: str
    name: str
    brand: str | None
    category_id: int | None
    category: str | None
    unit: Unit | None
    unit_amount: int | None
    vat: int | None
    search_text: str
    regular_price: Decimal
    promo_price: Decimal | None
    promo_start: dt.date | None
    promo_end: dt.date | None
    unit_price: Decimal | None
    price_date: dt.date
    current: bool


def open_csv(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open(encoding="utf-8-sig", newline="")


def source_columns(path: Path) -> list[str]:
    try:
        with open_csv(path) as file:
            header = file.readline().rstrip("\r\n").split(";")
    except UnicodeDecodeError as exc:
        raise SourceFormatError(f"CSV is not UTF-8: {exc}") from exc
    columns = [SOURCE_COLUMNS.get(normalize_text(h.strip('"')).replace("–", "-"), "") for h in header]
    if sorted(columns) != sorted(set(SOURCE_COLUMNS.values())):
        raise SourceFormatError(f"unexpected CSV header: {header}")
    return columns


def number(value: str | None) -> Decimal | None:
    return Decimal(value.replace(",", ".")) if value and NUMBER.fullmatch(value) else None


def day(value: str | None) -> dt.date | None:
    match = DATE.fullmatch(value or "")
    if not match:
        return None
    try:
        return dt.date(int(match[3]), int(match[2]), int(match[1]))
    except ValueError:
        return None


def search_text(name: str | None, brand: str | None) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", normalize_text(f"{name or ''} {brand or ''}"))


def source_row(values: dict[str, str | None]) -> SourceRow | None:
    regular_price = number(values.get("regular_price"))
    price_date = day(values.get("price_date"))
    current = LIST_TYPES.get((values.get("list_type") or "").upper())
    name = values.get("name")
    if not regular_price or price_date is None or current is None or not name:
        return None
    source_unit = (values.get("unit") or "").lower()
    unit, unit_amount = SOURCE_UNITS.get(source_unit, (None, None))
    promo_price = number(values.get("promo_price"))
    promo_price = promo_price if promo_price and promo_price < regular_price else None
    ean = values.get("ean")
    ean = None if ean and not ean.strip("0") else ean
    category_id = number(values.get("category_id"))
    vat = number(values.get("vat"))
    return SourceRow(
        store_format=values.get("store_format") or "",
        ean=ean,
        product_key=ean or name,
        name=name,
        brand=values.get("brand"),
        category_id=int(category_id) if category_id is not None else None,
        category=values.get("category"),
        unit=unit,
        unit_amount=unit_amount,
        vat=int(vat) if vat is not None else None,
        search_text=search_text(name, values.get("brand")),
        regular_price=regular_price,
        promo_price=promo_price,
        promo_start=day(values.get("promo_start")) if promo_price else None,
        promo_end=day(values.get("promo_end")) if promo_price else None,
        unit_price=number(values.get("unit_price")),
        price_date=price_date,
        current=current,
    )


def source_rows(path: Path) -> Iterator[SourceRow]:
    names = source_columns(path)
    try:
        with open_csv(path) as file:
            reader = csv.reader((line.replace("\x00", "") for line in file), delimiter=";", quotechar='"')
            next(reader, None)
            for values in reader:
                row = source_row(dict(zip(names, (value.strip() or None for value in values))))
                if row:
                    yield row
    except (UnicodeDecodeError, csv.Error) as exc:
        raise SourceFormatError(f"unreadable CSV: {exc}") from exc
