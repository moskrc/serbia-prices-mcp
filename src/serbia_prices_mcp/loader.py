import logging
import os
from collections.abc import Mapping
from pathlib import Path

import duckdb

from serbia_prices_mcp.repository import SCHEMA_SQL
from serbia_prices_mcp.retailers import RETAILERS
from serbia_prices_mcp.schemas import RetailerSync
from serbia_prices_mcp.source_format import SourceFormatError, source_columns

logger = logging.getLogger("serbia_prices_mcp")

LOAD_MACROS_SQL = r"""
CREATE OR REPLACE TEMP MACRO clean(x) AS nullif(trim(replace(replace(x, chr(0), ''), chr(9), ' ')), '');
CREATE OR REPLACE TEMP MACRO amount(x) AS
    CASE WHEN regexp_full_match(x, '\d+([.,]\d+)?') THEN CAST(replace(x, ',', '.') AS DECIMAL(12, 2)) END;
CREATE OR REPLACE TEMP MACRO day(x) AS
    CASE WHEN regexp_full_match(x, '\d{2}-\d{2}-\d{4}') THEN try_strptime(x, '%d-%m-%Y')::DATE END;
CREATE OR REPLACE TEMP MACRO fold(x) AS strip_accents(translate(
    replace(replace(replace(replace(replace(lower(x), 'đ', 'dj'), 'ђ', 'dj'), 'љ', 'lj'), 'њ', 'nj'), 'џ', 'dz'),
    'абвгдежзијклмнопрстћуфхцчш', 'abvgdezzijklmnoprstcufhccs'
));
"""

LOAD_SQL = """
INSERT INTO prices BY NAME
WITH cleaned AS (
    SELECT clean(store_format) AS store_format, clean(ean) AS ean, clean(name) AS name, clean(brand) AS brand,
           CAST(floor(amount(clean(category_id))) AS INTEGER) AS category_id, clean(category) AS category,
           amount(clean(regular_price)) AS regular_price, amount(clean(promo_price)) AS promo_price,
           day(clean(promo_end)) AS promo_end, day(clean(price_date)) AS price_date,
           CASE upper(clean(list_type)) WHEN 'VAZECI_CENOVNIK' THEN 'current' WHEN 'MESECNI_PRESEK' THEN 'monthly' END
               AS snapshot
    FROM read_csv(
        $path, delim = ';', quote = '"', escape = '"', header = true, names = $names, all_varchar = true,
        strict_mode = false, null_padding = true, ignore_errors = true
    )
), valid AS (
    SELECT *, CASE WHEN promo_price > 0 AND promo_price < regular_price THEN promo_price END AS promo
    FROM cleaned
    WHERE regular_price > 0 AND price_date IS NOT NULL AND snapshot IS NOT NULL AND name IS NOT NULL
)
SELECT $retailer AS retailer, coalesce(store_format, '') AS store_format,
       CASE WHEN NOT regexp_full_match(ean, '0+') THEN ean END AS ean,
       name, brand, category_id, category,
       ' ' || regexp_replace(fold(concat_ws(' ', name, brand)), '[^a-z0-9]+', ' ', 'g') AS search_text,
       regular_price, promo AS promo_price, CASE WHEN promo IS NOT NULL THEN promo_end END AS promo_end,
       coalesce(promo, regular_price) AS price, price_date, snapshot
FROM valid
"""


def load_prices(connection: duckdb.DuckDBPyConnection, retailer: str, source: Path) -> int:
    names = source_columns(source)
    connection.begin()
    try:
        connection.execute(LOAD_SQL, {"retailer": retailer, "path": str(source), "names": names})
        row = connection.execute(
            "SELECT count(*) FROM prices WHERE retailer = ? AND snapshot = 'current'", [retailer]
        ).fetchone()
        rows = int(row[0]) if row else 0
        if not rows:
            raise SourceFormatError("no valid current prices")
        connection.commit()
    except (duckdb.Error, SourceFormatError):
        connection.rollback()
        raise
    return rows


def build_database(path: Path, sources: Mapping[str, Path | str]) -> list[RetailerSync]:
    path.parent.mkdir(parents=True, exist_ok=True)
    building = path.with_name(f".{path.name}.{os.getpid()}.building")
    building.unlink(missing_ok=True)
    results = []
    try:
        with duckdb.connect(str(building)) as connection:
            connection.execute(SCHEMA_SQL)
            connection.execute(LOAD_MACROS_SQL)
            connection.executemany(
                "INSERT INTO retailers VALUES (?, ?, ?)", [(r.key, r.name, i) for i, r in enumerate(RETAILERS)]
            )
            for retailer, source in sources.items():
                if isinstance(source, str):
                    results.append(RetailerSync(retailer=retailer, status="error", error=source))
                    continue
                try:
                    rows = load_prices(connection, retailer, source)
                    results.append(RetailerSync(retailer=retailer, status="updated", rows=rows))
                except (duckdb.Error, SourceFormatError) as exc:
                    results.append(RetailerSync(retailer=retailer, status="error", error=f"{source.name}: {exc}"))
            failed = [r.retailer for r in results if r.status == "error"]
            if path.exists() and failed:
                try:
                    connection.execute(f"ATTACH '{str(path).replace("'", "''")}' AS previous (READ_ONLY)")
                    connection.execute(
                        "INSERT INTO prices BY NAME "
                        "SELECT * FROM previous.prices WHERE list_contains($failed, retailer)",
                        {"failed": failed},
                    )
                except duckdb.Error as exc:
                    logger.warning("previous prices of failed chains are not kept: %s", exc)
        if any(r.status == "updated" for r in results):
            building.replace(path)
    finally:
        building.unlink(missing_ok=True)
    return results
