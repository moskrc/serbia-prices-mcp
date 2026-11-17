import asyncio
import logging
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

from serbia_prices_mcp.loader import build_database
from serbia_prices_mcp.portal import DataPortal
from serbia_prices_mcp.retailers import RETAILERS, Retailer
from serbia_prices_mcp.schemas import RetailerSync

logger = logging.getLogger("serbia_prices_mcp")

MAX_AGE_SECONDS = 20 * 3600
CHECK_INTERVAL_SECONDS = 3600


class PriceSync:
    def __init__(self, path: Path, portal: DataPortal, retailers: Sequence[Retailer] = RETAILERS) -> None:
        self.path = path
        self.portal = portal
        self.retailers = retailers

    async def download(self, retailer: Retailer, directory: Path) -> Path | str:
        target = directory / f"{retailer.key}.csv"
        try:
            await self.portal.download(await self.portal.price_list_url(retailer), target)
        except Exception as exc:
            return str(exc)
        return target

    async def run(self) -> list[RetailerSync]:
        started = time.monotonic()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.path.parent) as directory:
            downloads = await asyncio.gather(*(self.download(r, Path(directory)) for r in self.retailers))
            sources: dict[str, Path | str] = {r.key: d for r, d in zip(self.retailers, downloads)}
            results = await asyncio.to_thread(build_database, self.path, sources)
        for result in results:
            if result.status == "error":
                logger.warning("%s: %s", result.retailer, result.error)
        updated = sum(r.status == "updated" for r in results)
        logger.info("prices updated for %d of %d chains in %.0fs", updated, len(results), time.monotonic() - started)
        return results

    def is_stale(self) -> bool:
        return not self.path.exists() or time.time() - self.path.stat().st_mtime > MAX_AGE_SECONDS

    async def run_forever(self) -> None:
        while True:
            if self.is_stale():
                try:
                    await self.run()
                except Exception:
                    logger.exception("price update failed")
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
