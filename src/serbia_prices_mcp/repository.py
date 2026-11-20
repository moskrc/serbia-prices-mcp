import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import duckdb

from serbia_prices_mcp.normalize import normalize_text
from serbia_prices_mcp.schemas import (
    BasketItem,
    BasketOption,
    Catalog,
    Discount,
    HistoryPoint,
    Offer,
    Page,
    RetailerInfo,
)

SCHEMA_SQL = """
CREATE TABLE prices (
    retailer VARCHAR NOT NULL, store_format VARCHAR NOT NULL, ean VARCHAR, name VARCHAR NOT NULL, brand VARCHAR,
    category_id INTEGER, category VARCHAR, search_text VARCHAR NOT NULL, regular_price DECIMAL(12, 2) NOT NULL,
    promo_price DECIMAL(12, 2), promo_end DATE, price DECIMAL(12, 2) NOT NULL, price_date DATE NOT NULL,
    snapshot VARCHAR NOT NULL
);
CREATE TABLE retailers (key VARCHAR NOT NULL, name VARCHAR NOT NULL, position INTEGER NOT NULL);
CREATE MACRO norm(x) AS strip_accents(replace(lower(x), 'đ', 'dj'));
CREATE MACRO matches(text, tokens) AS list_bool_and([contains(text, ' ' || t) FOR t IN tokens]);
CREATE MACRO relevance(text, token) AS
    CASE
        WHEN starts_with(text, ' ' || token) THEN 2
        WHEN regexp_matches(text, '^ [a-z0-9]+ ' || token) THEN 1
        ELSE 0
    END;
CREATE MACRO in_chains(label, chains) AS chains IS NULL OR list_bool_or([contains(norm(label), c) FOR c IN chains]);
CREATE MACRO in_category(category_id, category, wanted) AS
    wanted IS NULL OR CAST(category_id AS VARCHAR) = wanted OR contains(norm(category), wanted);
"""

PRODUCT_COLUMNS = "retailer, ean, name, brand, category, price, regular_price, promo_price, promo_end, price_date"

STORE_FORMATS = "list_sort(list(DISTINCT store_format)) AS store_formats"

CHAIN_FILTER = "in_chains(concat_ws(' ', r.key, r.name, p.store_format), $chains)"

PRICES = """(
    SELECT * EXCLUDE (expired) REPLACE (
        if(expired, NULL, promo_price) AS promo_price,
        if(expired, NULL, promo_end) AS promo_end,
        if(expired, regular_price, price) AS price
    )
    FROM (SELECT *, coalesce(snapshot = 'current' AND promo_end < current_date, false) AS expired FROM prices)
)"""

SEARCH_SQL = f"""
WITH matched AS (
    SELECT p.*, list_max([relevance(p.search_text, v[1]) FOR v IN $variants]) AS relevant
    FROM {PRICES} p JOIN retailers r ON r.key = p.retailer
    WHERE p.snapshot = 'current'
      AND list_bool_or([matches(p.search_text, v) FOR v IN $variants])
      AND {CHAIN_FILTER}
      AND in_category(p.category_id, p.category, $category)
), grouped AS (
    SELECT {PRODUCT_COLUMNS}, relevant, {STORE_FORMATS} FROM matched GROUP BY ALL
)
SELECT * FROM grouped
QUALIFY row_number() OVER (PARTITION BY retailer, coalesce(ean, name) ORDER BY price, store_formats) = 1
ORDER BY relevant DESC, price, retailer, name, ean
"""

COMPARE_SQL = f"""
WITH matched AS (
    SELECT p.* FROM {PRICES} p JOIN retailers r ON r.key = p.retailer
    WHERE p.snapshot = 'current' AND p.ean = $ean AND {CHAIN_FILTER}
), grouped AS (
    SELECT {PRODUCT_COLUMNS}, {STORE_FORMATS} FROM matched GROUP BY ALL
)
SELECT *,
       round(price - min(price) OVER (), 2) AS diff_rsd,
       round(100 * (price - min(price) OVER ()) / min(price) OVER (), 2) AS diff_pct
FROM grouped ORDER BY price, retailer, store_formats, name
"""

HISTORY_SQL = f"""
SELECT p.retailer, p.price_date, p.snapshot, p.regular_price, p.promo_price, p.price, {STORE_FORMATS}
FROM {PRICES} p JOIN retailers r ON r.key = p.retailer
WHERE p.ean = $ean AND {CHAIN_FILTER}
GROUP BY ALL
ORDER BY p.retailer, store_formats, p.price_date, p.snapshot
"""

DISCOUNTS_SQL = f"""
WITH history AS (
    SELECT retailer, store_format, ean, min(regular_price) AS min_regular, min(price) AS min_price
    FROM prices WHERE snapshot = 'monthly' AND ean IS NOT NULL GROUP BY ALL
), matched AS (
    SELECT p.*,
           round(100 * (p.regular_price - p.promo_price) / p.regular_price, 2) AS discount_pct,
           least(h.min_price, p.price) AS lowest_recent_price,
           coalesce(p.regular_price > h.min_regular * 1.02, false) AS regular_raised_before_promo,
           100 * (p.regular_price - p.promo_price) / p.regular_price >= 80 AS needs_verification
    FROM {PRICES} p
    JOIN retailers r ON r.key = p.retailer
    LEFT JOIN history h ON h.retailer = p.retailer AND h.store_format = p.store_format AND h.ean = p.ean
    WHERE p.snapshot = 'current' AND p.promo_price IS NOT NULL
      AND 100 * (p.regular_price - p.promo_price) / p.regular_price >= $min_discount_pct
      AND {CHAIN_FILTER}
      AND in_category(p.category_id, p.category, $category)
), grouped AS (
    SELECT {PRODUCT_COLUMNS}, discount_pct, lowest_recent_price, regular_raised_before_promo, needs_verification,
           {STORE_FORMATS}
    FROM matched GROUP BY ALL
)
SELECT * FROM grouped
QUALIFY row_number() OVER (
    PARTITION BY retailer, coalesce(ean, name) ORDER BY discount_pct DESC, price, store_formats
) = 1
ORDER BY discount_pct DESC, price, retailer, name, ean
"""

BASKET_SQL = f"""
WITH items AS (
    SELECT i, $labels[i] AS label, $tokens[i] AS tokens, $eans[i] AS ean, $quantities[i] AS quantity
    FROM range(1, len($labels) + 1) t(i)
), matched AS (
    SELECT i.i, i.label, i.quantity, p.retailer, p.store_format, p.name, p.ean, p.price,
           CASE WHEN i.ean <> '' THEN 2 ELSE relevance(p.search_text, i.tokens[1]) END AS relevant
    FROM items i
    JOIN {PRICES} p ON p.snapshot = 'current'
        AND CASE WHEN i.ean <> '' THEN p.ean = i.ean ELSE matches(p.search_text, i.tokens) END
    JOIN retailers r ON r.key = p.retailer
    WHERE {CHAIN_FILTER}
    QUALIFY relevant = max(relevant) OVER (PARTITION BY i.i)
), picks AS (
    SELECT * FROM matched
    QUALIFY row_number() OVER (PARTITION BY i, retailer, store_format ORDER BY price, name) = 1
), totals AS (
    SELECT retailer, store_format, sum(price * quantity) AS total, count(*) AS found,
           list({{
               'i': i, 'item': label, 'name': name, 'ean': ean, 'price': price, 'quantity': quantity,
               'cost': price * quantity
           }} ORDER BY i) AS picks
    FROM picks GROUP BY retailer, store_format
)
SELECT *, [$labels[n] FOR n IN range(1, len($labels) + 1) IF NOT list_contains([p.i FOR p IN picks], n)] AS missing
FROM totals ORDER BY found DESC, total, store_format LIMIT 10
"""

CATALOG_SQL = f"""
SELECT p.retailer AS key, any_value(r.name) AS name, {STORE_FORMATS},
       count(DISTINCT coalesce(p.ean, p.name)) AS products, max(p.price_date) AS price_date
FROM prices p JOIN retailers r ON r.key = p.retailer
WHERE p.snapshot = 'current'
GROUP BY p.retailer ORDER BY min(r.position)
"""

CATEGORIES_SQL = """
SELECT max(category) AS name FROM prices
WHERE snapshot = 'current' AND category_id IS NOT NULL
GROUP BY category_id ORDER BY category_id
"""


class DataNotReady(Exception):
    pass


def query_tokens(queries: Sequence[str]) -> list[list[str]]:
    tokens = [
        [t for word in normalize_text(q).split() if word.isascii() for t in re.findall(r"[a-z0-9]+", word)]
        for q in queries
    ]
    return [t for t in tokens if t]


def chain_names(chains: Sequence[str] | None) -> list[str] | None:
    names = [normalize_text(c) for c in chains or [] if normalize_text(c)]
    return names or None


def rows(connection: duckdb.DuckDBPyConnection, sql: str, params: Mapping[str, object]) -> list[dict[str, Any]]:
    result = connection.execute(sql, params)
    columns = [d[0] for d in result.description or []]
    return [dict(zip(columns, row)) for row in result.fetchall()]


class PriceRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> duckdb.DuckDBPyConnection:
        if not self.path.exists():
            raise DataNotReady("Prices are being downloaded from data.gov.rs for the first time, retry in a minute.")
        return duckdb.connect(str(self.path), read_only=True)

    def fetch(self, sql: str, params: Mapping[str, object]) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return rows(connection, sql, params)

    def page(self, sql: str, params: Mapping[str, object], limit: int, offset: int) -> dict[str, Any]:
        with self.connect() as connection:
            (count,) = rows(connection, f"SELECT count(*) AS total FROM ({sql})", params)
            items = rows(connection, f"{sql} LIMIT $limit OFFSET $offset", {**params, "limit": limit, "offset": offset})
        return {"items": items, "total": count["total"], "limit": limit, "offset": offset}

    def search(
        self,
        queries: Sequence[str],
        chains: Sequence[str] | None = None,
        category: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Page[Offer]:
        variants = query_tokens(queries)
        if not variants:
            return Page[Offer](items=[], total=0, limit=limit, offset=offset)
        params = {"variants": variants, "chains": chain_names(chains), "category": normalize_text(category) or None}
        return Page[Offer].model_validate(self.page(SEARCH_SQL, params, limit, offset))

    def compare_by_barcode(
        self, ean: str, chains: Sequence[str] | None = None, limit: int = 20, offset: int = 0
    ) -> Page[Offer]:
        params = {"ean": ean.strip(), "chains": chain_names(chains)}
        return Page[Offer].model_validate(self.page(COMPARE_SQL, params, limit, offset))

    def price_history(
        self, ean: str, chains: Sequence[str] | None = None, limit: int = 20, offset: int = 0
    ) -> Page[HistoryPoint]:
        params = {"ean": ean.strip(), "chains": chain_names(chains)}
        return Page[HistoryPoint].model_validate(self.page(HISTORY_SQL, params, limit, offset))

    def top_discounts(
        self,
        category: str | None = None,
        min_discount_pct: float = 25,
        chains: Sequence[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Page[Discount]:
        params = {
            "category": normalize_text(category) or None,
            "min_discount_pct": min_discount_pct,
            "chains": chain_names(chains),
        }
        return Page[Discount].model_validate(self.page(DISCOUNTS_SQL, params, limit, offset))

    def optimize_basket(self, items: Sequence[BasketItem], chains: Sequence[str] | None = None) -> list[BasketOption]:
        tokenized = [(item, (query_tokens([item.query]) or [[]])[0]) for item in items]
        wanted = [(item, tokens) for item, tokens in tokenized if tokens or (item.ean or "").strip()]
        if not wanted:
            return []
        params = {
            "labels": [item.query for item, _ in wanted],
            "tokens": [tokens or [""] for _, tokens in wanted],
            "eans": [(item.ean or "").strip() for item, _ in wanted],
            "quantities": [item.quantity for item, _ in wanted],
            "chains": chain_names(chains),
        }
        return [BasketOption.model_validate(row) for row in self.fetch(BASKET_SQL, params)]

    def catalog(self) -> Catalog:
        return Catalog(
            retailers=[RetailerInfo.model_validate(row) for row in self.fetch(CATALOG_SQL, {})],
            categories=[row["name"] for row in self.fetch(CATEGORIES_SQL, {})],
        )
