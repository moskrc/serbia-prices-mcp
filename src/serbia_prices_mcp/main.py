import argparse
import asyncio
import logging
import sys

import httpx

from serbia_prices_mcp.config import Settings
from serbia_prices_mcp.portal import DataPortal
from serbia_prices_mcp.repository import PriceRepository
from serbia_prices_mcp.server import build_server
from serbia_prices_mcp.sync import PriceSync


def main() -> None:
    parser = argparse.ArgumentParser(prog="serbia-prices-mcp", description="MCP server for grocery prices in Serbia.")
    parser.add_argument(
        "command", nargs="?", choices=["serve", "sync"], default="serve",
        help="serve: run the MCP server (default); sync: download today's price lists now and exit",
    )
    command = parser.parse_args().command
    settings = Settings()
    logging.basicConfig(level=settings.log_level, stream=sys.stderr, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    client = httpx.AsyncClient(
        follow_redirects=True, timeout=httpx.Timeout(30, read=300), headers={"User-Agent": "serbia-prices-mcp"}
    )
    database = settings.data_dir / "prices.duckdb"
    sync = PriceSync(database, DataPortal(client))
    if command == "sync":
        results = asyncio.run(sync.run())
        sys.exit(0 if any(r.status == "updated" for r in results) else 1)
    server = build_server(PriceRepository(database), sync)
    if settings.transport == "http":
        server.run(transport="http", host=settings.host, port=settings.port, show_banner=False)
    else:
        server.run(show_banner=False)
