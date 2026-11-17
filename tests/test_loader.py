from collections.abc import Callable
from pathlib import Path

import pytest

from serbia_prices_mcp.loader import build_database
from serbia_prices_mcp.repository import PriceRepository
from serbia_prices_mcp.schemas import RetailerSync


@pytest.mark.usefixtures("sample")
def test_failed_retailers_keep_previous_prices(
    tmp_path: Path, price_csv: Callable[..., Path], database: Path, repository: PriceRepository
) -> None:
    broken = tmp_path / "delhaize-broken.csv"
    broken.write_text("Naziv;Cena\nx;1\n", encoding="utf-8")
    lidl = price_csv("lidl-new.csv", [
        "1;Mleko, mlečni i mešoviti proizvodi, jaja;Jaja M 10 kom;Lidl;4056489000002;kom.;Lidl Srbija KD;17-11-2026;219.99;22.00;;;;10;VAZECI_CENOVNIK",
    ])

    results = build_database(database, {"lidl": lidl, "delhaize": broken, "univerexport": "download failed"})

    assert [(r.retailer, r.status, r.rows) for r in results] == [
        ("lidl", "updated", 1), ("delhaize", "error", None), ("univerexport", "error", None)
    ]
    assert results[2] == RetailerSync(retailer="univerexport", status="error", error="download failed")
    assert {r.key: r.products for r in repository.catalog().retailers} == {"lidl": 1, "delhaize": 4, "univerexport": 4}
    assert [p.name for p in database.parent.iterdir()] == ["prices.duckdb"]


def test_nothing_loaded_leaves_database_untouched(database: Path) -> None:
    results = build_database(database, {"lidl": "download failed"})

    assert [r.status for r in results] == ["error"]
    assert not database.exists()


def test_unknown_unit_does_not_reject_retailer(price_csv: Callable[..., Path], database: Path) -> None:
    rows = ["1;Mleko;Mleko 1l;Imlek;8600000000001;bure;IDEA;16-11-2026;129.99;129.99;;;;20;VAZECI_CENOVNIK"]

    (result,) = build_database(database, {"idea": price_csv("idea.csv", rows)})

    assert (result.status, result.rows) == ("updated", 1)


def test_unreadable_previous_database_is_replaced(
    database: Path, sample_sources: dict[str, Path | str], repository: PriceRepository
) -> None:
    database.parent.mkdir(parents=True)
    database.write_bytes(b"not a duckdb file")

    results = build_database(database, {**sample_sources, "idea": "download failed"})

    assert [r.status for r in results] == ["updated", "updated", "updated", "error"]
    assert [r.key for r in repository.catalog().retailers] == ["lidl", "delhaize", "univerexport"]


@pytest.mark.usefixtures("sample")
def test_rebuild_replaces_prices_without_duplicates(
    database: Path, sample_sources: dict[str, Path | str], repository: PriceRepository
) -> None:
    assert [r.status for r in build_database(database, sample_sources)] == ["updated"] * 3
    assert {r.key: r.products for r in repository.catalog().retailers} == {"lidl": 4, "delhaize": 4, "univerexport": 4}
