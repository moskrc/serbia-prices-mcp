from pathlib import Path

import httpx

from conftest import LIDL, STANDARD_HEADER
from serbia_prices_mcp.portal import DataPortal
from serbia_prices_mcp.repository import PriceRepository
from serbia_prices_mcp.retailers import RETAILERS
from serbia_prices_mcp.sync import PriceSync

CHAINS = RETAILERS[:3]


def portal(handler: httpx.MockTransport) -> DataPortal:
    return DataPortal(httpx.AsyncClient(transport=handler))


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/1/datasets/":
        organization = request.url.params["organization"]
        url = "relative.csv" if organization == CHAINS[2].organization_id else f"https://shop.rs/{organization}.csv"
        resource = {"title": "Cene proizvoda", "format": "csv", "url": url}
        return httpx.Response(200, json={"data": [{"resources": [resource]}]})
    if request.url.path == f"/{CHAINS[0].organization_id}.csv":
        return httpx.Response(200, content="\n".join([STANDARD_HEADER, *LIDL]).encode())
    return httpx.Response(500)


async def test_sync_loads_downloaded_chains_and_reports_failed(database: Path, repository: PriceRepository) -> None:
    sync = PriceSync(database, portal(httpx.MockTransport(handler)), CHAINS)

    results = await sync.run()

    assert [(r.retailer, r.status) for r in results] == [("lidl", "updated"), ("delhaize", "error"), ("idea", "error")]
    assert "download failed" in (results[1].error or "")
    assert [r.key for r in repository.catalog().retailers] == ["lidl"]
    assert [p.name for p in database.parent.iterdir()] == ["prices.duckdb"]
    assert not sync.is_stale()


def test_missing_database_is_stale(database: Path) -> None:
    assert PriceSync(database, portal(httpx.MockTransport(handler))).is_stale()
