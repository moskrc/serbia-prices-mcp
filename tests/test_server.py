from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastmcp import Client

from serbia_prices_mcp.portal import DataPortal
from serbia_prices_mcp.repository import PriceRepository
from serbia_prices_mcp.server import build_server
from serbia_prices_mcp.sync import PriceSync


@pytest.fixture
async def client(database: Path, repository: PriceRepository) -> AsyncIterator[Client[Any]]:
    offline = DataPortal(httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(503))))
    async with Client(build_server(repository, PriceSync(database, offline))) as mcp:
        yield mcp


async def test_tools_are_read_only(client: Client[Any]) -> None:
    hints = {t.name: bool(t.annotations and t.annotations.read_only_hint) for t in await client.list_tools()}

    assert hints == {
        "get_price_history": True,
        "get_top_discounts": True,
        "list_retailers_and_categories": True,
        "optimize_basket": True,
        "search_products": True,
    }


@pytest.mark.usefixtures("sample")
async def test_tools_answer_from_local_database(client: Client[Any]) -> None:
    search = await client.call_tool("search_products", {"query": ["maslac"], "retail_chains": ["Lidl"], "limit": 5})
    basket = await client.call_tool("optimize_basket", {"items": [{"query": "jaja", "quantity": 2}]})

    assert search.structured_content is not None
    assert [p["name"] for p in search.structured_content["items"]] == ["Maslac 82% Pilos 250g"]
    assert basket.structured_content is not None
    assert basket.structured_content["result"][0]["total"] == 459.98


@pytest.mark.usefixtures("sample")
async def test_search_by_barcode_compares_the_product_across_store_formats(client: Client[Any]) -> None:
    by_name = await client.call_tool("search_products", {"query": ["lurpak"]})
    by_barcode = await client.call_tool("search_products", {"ean": "8600000000101", "retail_chains": ["Maxi"]})

    assert by_name.structured_content is not None
    assert {p["diff_rsd"] for p in by_name.structured_content["items"]} == {None}
    assert by_barcode.structured_content is not None
    assert [(p["store_formats"], p["diff_rsd"]) for p in by_barcode.structured_content["items"]] == [
        (["Mega Maxi"], 0.0), (["Maxi"], 20.0)
    ]


async def test_search_needs_query_or_barcode(client: Client[Any]) -> None:
    with pytest.raises(Exception, match="query or ean"):
        await client.call_tool("search_products", {})


async def test_tools_ask_to_retry_while_first_download_runs(client: Client[Any]) -> None:
    with pytest.raises(Exception, match="retry in a minute"):
        await client.call_tool("list_retailers_and_categories", {})
