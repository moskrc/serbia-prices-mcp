import datetime as dt
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

Query = Annotated[
    list[str] | None,
    Field(description="Serbian Latin product name plus optional synonyms, e.g. ['pileci file']. Not needed with ean."),
]
Chains = Annotated[
    list[str] | None,
    Field(description="Optional chain or store format names to restrict results, e.g. ['Lidl', 'Maxi', 'Idea']."),
]
Category = Annotated[str | None, Field(description="Optional category name or number 1-25.")]
Limit = Annotated[int, Field(ge=1, le=100, description="Page size.")]
Offset = Annotated[int, Field(ge=0, description="Number of results to skip.")]
Ean = Annotated[str, Field(description="EAN barcode from search results.")]
EanFilter = Annotated[
    str | None,
    Field(description="EAN barcode from earlier results: compare this exact product across all chains and formats."),
]
DiscountPct = Annotated[float, Field(ge=0, le=100)]


class BasketItem(BaseModel):
    query: str = Field(min_length=1, description="Serbian Latin product name, e.g. 'pileci file'.")
    quantity: int = Field(ge=1, description="Number of packages to buy.")
    ean: str | None = Field(default=None, description="Barcode from search results to buy exactly this product.")


BasketItems = Annotated[list[BasketItem], Field(min_length=1, max_length=30)]


class ProductPrice(BaseModel):
    retailer: str
    store_formats: list[str]
    name: str
    brand: str | None
    ean: str | None
    category: str | None
    price: float
    regular_price: float
    promo_price: float | None
    promo_end: dt.date | None
    price_date: dt.date


class Offer(ProductPrice):
    diff_rsd: float | None = None
    diff_pct: float | None = None


class Discount(ProductPrice):
    discount_pct: float
    lowest_recent_price: float | None
    regular_raised_before_promo: bool
    needs_verification: bool


class HistoryPoint(BaseModel):
    retailer: str
    store_formats: list[str]
    price_date: dt.date
    snapshot: Literal["current", "monthly"]
    regular_price: float
    promo_price: float | None
    price: float


class BasketPick(BaseModel):
    item: str
    name: str
    ean: str | None
    price: float
    quantity: int
    cost: float


class BasketOption(BaseModel):
    retailer: str
    store_format: str
    total: float
    found: int
    missing: list[str]
    picks: list[BasketPick]


class RetailerInfo(BaseModel):
    key: str
    name: str
    store_formats: list[str]
    products: int
    price_date: dt.date | None


class Catalog(BaseModel):
    retailers: list[RetailerInfo]
    categories: list[str]


class RetailerSync(BaseModel):
    retailer: str
    status: Literal["updated", "error"]
    rows: int | None = None
    error: str | None = None


Item = TypeVar("Item")


class Page(BaseModel, Generic[Item]):
    items: list[Item]
    total: int = Field(description="Number of items on all pages.")
    limit: int
    offset: int
