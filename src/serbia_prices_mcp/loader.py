import csv
import logging
import os
from collections.abc import Mapping
from pathlib import Path

import duckdb

from serbia_prices_mcp.repository import SCHEMA_SQL
from serbia_prices_mcp.retailers import RETAILERS
from serbia_prices_mcp.schemas import RetailerSync
from serbia_prices_mcp.source_format import SourceFormatError, source_rows

logger = logging.getLogger("serbia_prices_mcp")

STAGING_COLUMNS = (
    "{'store_format': 'VARCHAR', 'ean': 'VARCHAR', 'name': 'VARCHAR', 'brand': 'VARCHAR', 'category_id': 'INTEGER', "
    "'category': 'VARCHAR', 'search_text': 'VARCHAR', 'regular_price': 'DECIMAL(12, 2)', "
    "'promo_price': 'DECIMAL(12, 2)', 'promo_end': 'DATE', 'price_date': 'DATE', 'snapshot': 'VARCHAR'}"
)

LOAD_SQL = f"""
INSERT INTO prices BY NAME
SELECT $retailer AS retailer, * REPLACE (coalesce(store_format, '') AS store_format),
       coalesce(promo_price, regular_price) AS price
FROM read_csv($path, header = false, delim = ',', quote = '"', escape = '"', columns = {STAGING_COLUMNS})
"""


def write_staging(source: Path, staging: Path) -> None:
    with staging.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        for row in source_rows(source):
            writer.writerow((
                row.store_format, row.ean, row.name, row.brand, row.category_id, row.category, row.search_text,
                row.regular_price, row.promo_price, row.promo_end, row.price_date,
                "current" if row.current else "monthly",
            ))


def load_prices(connection: duckdb.DuckDBPyConnection, retailer: str, source: Path, staging: Path) -> int:
    write_staging(source, staging)
    connection.begin()
    try:
        connection.execute(LOAD_SQL, {"retailer": retailer, "path": str(staging)})
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
    staging = path.with_name(f".{path.name}.{os.getpid()}.csv")
    building.unlink(missing_ok=True)
    results = []
    try:
        with duckdb.connect(str(building)) as connection:
            connection.execute(SCHEMA_SQL)
            connection.executemany(
                "INSERT INTO retailers VALUES (?, ?, ?)", [(r.key, r.name, i) for i, r in enumerate(RETAILERS)]
            )
            for retailer, source in sources.items():
                if isinstance(source, str):
                    results.append(RetailerSync(retailer=retailer, status="error", error=source))
                    continue
                try:
                    rows = load_prices(connection, retailer, source, staging)
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
        staging.unlink(missing_ok=True)
    return results
