from pathlib import Path

import httpx
import pytest

from serbia_prices_mcp.retailers import Retailer
from serbia_prices_mcp.portal import DataPortal, PortalError

LIDL = Retailer(key="lidl", name="Lidl", organization_id="68f0ece19e69a823f887080b")

LIDL_DATASETS = {
    "data": [
        {
            "id": "68f61917f9daecc02d803b84",
            "resources": [
                {
                    "title": "EAN",
                    "format": "csv",
                    "last_modified": "2026-10-22T08:17:27.760000+00:00",
                    "url": "https://www.lidl.rs/explore/assets/webPriceData/rs/EAN.csv",
                },
                {
                    "title": "cene_proizvoda_lidl.csv",
                    "format": "csv",
                    "last_modified": "2026-10-22T08:08:09.000000+00:00",
                    "url": "https://www.lidl.rs/explore/assets/webPriceData/rs/cene_proizvoda_Lidl.csv",
                },
                {
                    "title": "Cene proizvoda arhiva",
                    "format": "xlsx",
                    "last_modified": "2026-11-01T00:00:00+00:00",
                    "url": "https://example.rs/arhiva.xlsx",
                },
            ],
        }
    ]
}


async def test_resolve_picks_price_csv_of_organization() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/1/datasets/"
        assert request.url.params["organization"] == LIDL.organization_id
        return httpx.Response(200, json=LIDL_DATASETS)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        url = await DataPortal(client).price_list_url(LIDL)

    assert url == "https://www.lidl.rs/explore/assets/webPriceData/rs/cene_proizvoda_Lidl.csv"


async def test_resolve_fails_without_price_csv() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"data": []}))

    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(PortalError):
            await DataPortal(client).price_list_url(LIDL)


async def test_download_follows_redirect_and_replaces_file(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "data.gov.rs":
            return httpx.Response(302, headers={"Location": "https://cdn.example.rs/prices.csv"})
        return httpx.Response(200, content=b"csv-body")

    target = tmp_path / "raw" / "lidl.csv"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        await DataPortal(client).download("https://data.gov.rs/r/1", target)

    assert target.read_bytes() == b"csv-body"
    assert list(target.parent.iterdir()) == [target]


async def test_download_http_error_keeps_previous_file(tmp_path: Path) -> None:
    target = tmp_path / "p.csv"
    target.write_bytes(b"old")
    transport = httpx.MockTransport(lambda request: httpx.Response(500))

    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(PortalError):
            await DataPortal(client).download("https://x.rs/p.csv", target)

    assert target.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [target]


async def test_resolve_fails_on_non_json_response() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"<html>maintenance</html>"))

    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(PortalError):
            await DataPortal(client).price_list_url(LIDL)


@pytest.mark.parametrize(
    "title",
    ["Ценовници производа према Правилнику", "Исправљени ценовник (13.11.2026)", "cene-proizvoda-aksa-16-11-2026.csv"],
)
async def test_resolve_accepts_cyrillic_and_dated_titles(title: str) -> None:
    resources = [
        {"title": "EAN", "format": "csv", "last_modified": "2026-11-17", "url": "https://x.rs/ean.csv"},
        {"title": title, "format": "csv", "last_modified": "2026-11-16", "url": "https://x.rs/prices.csv"},
    ]
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"data": [{"resources": resources}]}))

    async with httpx.AsyncClient(transport=transport) as client:
        assert await DataPortal(client).price_list_url(LIDL) == "https://x.rs/prices.csv"
