from pathlib import Path

import httpx

from serbia_prices_mcp.normalize import normalize_text
from serbia_prices_mcp.retailers import Retailer

PORTAL_API_URL = "https://data.gov.rs/api/1"


class PortalError(Exception):
    pass


class DataPortal:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def price_list_url(self, retailer: Retailer) -> str:
        try:
            response = await self.client.get(
                f"{PORTAL_API_URL}/datasets/",
                params={"organization": retailer.organization_id, "page_size": 50},
            )
            response.raise_for_status()
            datasets = response.json().get("data", [])
        except (httpx.HTTPError, ValueError) as exc:
            raise PortalError(f"{retailer.key}: portal API request failed: {exc}") from exc
        candidates = [
            resource
            for dataset in datasets
            for resource in dataset.get("resources", [])
            if str(resource.get("format", "")).lower() == "csv"
            and "cen" in normalize_text(resource.get("title"))
            and resource.get("url")
        ]
        if not candidates:
            raise PortalError(f"{retailer.key}: no price list CSV found on data.gov.rs")
        latest = max(candidates, key=lambda resource: str(resource.get("last_modified") or ""))
        return str(latest["url"])

    async def download(self, url: str, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.tmp")
        try:
            async with self.client.stream("GET", url) as response:
                response.raise_for_status()
                with tmp.open("wb") as file:
                    async for chunk in response.aiter_bytes():
                        file.write(chunk)
            tmp.replace(target)
        except httpx.HTTPError as exc:
            raise PortalError(f"download failed for {url}: {exc}") from exc
        finally:
            tmp.unlink(missing_ok=True)
