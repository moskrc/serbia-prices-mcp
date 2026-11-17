import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp_types import ToolAnnotations

from serbia_prices_mcp.repository import PriceRepository
from serbia_prices_mcp.schemas import (
    BasketItems,
    BasketOption,
    Catalog,
    Category,
    Chains,
    Discount,
    DiscountPct,
    Ean,
    EanFilter,
    HistoryPoint,
    Limit,
    Offer,
    Offset,
    Page,
    Query,
)
from serbia_prices_mcp.sync import PriceSync

INSTRUCTIONS = (
    "Grocery prices of the major retail chains of Belgrade and Novi Sad (Lidl, Maxi, Mega Maxi, Shop&Go, Idea, "
    "Mercator, Roda, Univerexport, Gomex, Aman, Metro, dm, Aroma, Svetofor, Veropoulos) "
    "from official open data at data.gov.rs, updated daily. Prices are in RSD. "
    "Product names in the data are Serbian (Latin script). Always translate the user's product words from any "
    "language into Serbian Latin before calling a tool, e.g. 'куриное филе' / 'chicken breast' -> 'pileci file', "
    "'масло сливочное' / 'butter' -> 'maslac', 'яйца' / 'eggs' -> 'jaja', 'рис' / 'rice' -> 'pirinac'. "
    "Lists are paged: 'total' is the number of all results, pass 'offset' to get the next page. "
    "When answering, name the source: price lists published by the chains on data.gov.rs (Serbian Open Data "
    "License), with the price date; prices are shown as published and may differ in the store."
)

READ_ONLY = ToolAnnotations(read_only_hint=True)


def build_server(repository: PriceRepository, sync: PriceSync) -> FastMCP:
    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[None]:
        task = asyncio.create_task(sync.run_forever())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    mcp = FastMCP("serbia-prices", instructions=INSTRUCTIONS, lifespan=lifespan)

    @mcp.tool(
        description=(
            "Search current product prices across Serbian chains. Pass the product name in Serbian Latin "
            "(translate from Russian/English first) and optionally synonyms as extra list items. "
            "Most relevant names first, then the cheapest shelf price (price of the package as sold). "
            "If nothing is found, retry with a synonym or a more general word. "
            "Pass ean instead of query to compare one exact product across all chains and store formats: "
            "results are sorted by price, diff_rsd and diff_pct show the difference from the cheapest."
        ),
        annotations=READ_ONLY,
    )
    def search_products(
        query: Query = None,
        ean: EanFilter = None,
        retail_chains: Chains = None,
        category: Category = None,
        limit: Limit = 20,
        offset: Offset = 0,
    ) -> Page[Offer]:
        if ean:
            return repository.compare_by_barcode(ean, retail_chains, limit, offset)
        if not query:
            raise ToolError("Pass query or ean.")
        return repository.search(query, retail_chains, category, limit, offset)

    @mcp.tool(
        description=(
            "Estimate grocery basket cost per store. Each item has a Serbian Latin query and the number of "
            "packages, e.g. {'query': 'jaja', 'quantity': 1}. Without ean, every store gets the cheapest package "
            "whose name matches, which may be a different product (chocolate milk for 'mleko'). For an exact "
            "product, first find it with search_products, let the user choose, then pass its ean: "
            "{'query': 'mleko 2.8% 1l', 'ean': '860...', 'quantity': 2}. Cost is price x quantity; "
            "stores with all items come first."
        ),
        annotations=READ_ONLY,
    )
    def optimize_basket(items: BasketItems, preferred_chains: Chains = None) -> list[BasketOption]:
        return repository.optimize_basket(items, preferred_chains)

    @mcp.tool(
        description=(
            "Current promotions with discount of at least min_discount_pct, as published by the chains. "
            "regular_raised_before_promo=true means the regular price was raised compared to the monthly snapshots "
            "of recent months, so the discount may be inflated; false does NOT confirm the discount is real. "
            "needs_verification=true marks discounts of 80% or more: usually clearance of leftover stock or a data "
            "error in the published price list; warn the user to check in the store."
        ),
        annotations=READ_ONLY,
    )
    def get_top_discounts(
        category: Category = None,
        min_discount_pct: DiscountPct = 25,
        retail_chains: Chains = None,
        limit: Limit = 20,
        offset: Offset = 0,
    ) -> Page[Discount]:
        return repository.top_discounts(category, min_discount_pct, retail_chains, limit, offset)

    @mcp.tool(
        description=(
            "Price history of a product by EAN from the price lists on data.gov.rs: monthly snapshots published by "
            "the chains (snapshot='monthly') and today's list (snapshot='current')."
        ),
        annotations=READ_ONLY,
    )
    def get_price_history(
        ean: Ean, retail_chains: Chains = None, limit: Limit = 20, offset: Offset = 0
    ) -> Page[HistoryPoint]:
        return repository.price_history(ean, retail_chains, limit, offset)

    @mcp.tool(
        description="List available chains, their store formats, data dates and the 25 product categories.",
        annotations=READ_ONLY,
    )
    def list_retailers_and_categories() -> Catalog:
        return repository.catalog()

    return mcp
