import datetime as dt
from collections.abc import Callable
from pathlib import Path

import pytest

from serbia_prices_mcp.loader import build_database
from serbia_prices_mcp.repository import DataNotReady, PriceRepository
from serbia_prices_mcp.schemas import BasketItem


@pytest.mark.usefixtures("sample")
@pytest.mark.parametrize("query", ["pileci file", "Pileći FILE"])
def test_search_matches_across_spellings_sorted_by_package_price(repository: PriceRepository, query: str) -> None:
    results = repository.search([query]).items

    assert [(r.retailer, r.price) for r in results] == [("delhaize", 449.99), ("univerexport", 729.99), ("lidl", 779.99)]


@pytest.mark.usefixtures("sample")
def test_search_ranks_names_starting_with_query_first(repository: PriceRepository) -> None:
    names = [r.name for r in repository.search(["maslac"]).items]

    assert names[0] == "Maslac 82% Pilos 250g"
    assert names[-1] == "Keks sa maslacem 200g"


@pytest.mark.usefixtures("sample")
def test_search_collapses_store_formats_to_cheapest(repository: PriceRepository) -> None:
    (lurpak,) = [r for r in repository.search(["lurpak"]).items if r.retailer == "delhaize"]

    assert lurpak.store_formats == ["Mega Maxi"]
    assert lurpak.price == 479.99


@pytest.mark.usefixtures("sample")
def test_search_synonyms_filters_and_paging(repository: PriceRepository) -> None:
    assert {r.ean for r in repository.search(["pileca prsa", "jaja"]).items} == {"8600000000104", "4056489000002"}
    assert {r.retailer for r in repository.search(["pileci file"], chains=["Maxi"]).items} == {"delhaize"}
    assert {r.ean for r in repository.search(["maslac"], category="ulja").items} == {"8600000000101", "4056489000001"}
    page = repository.search(["maslac"], limit=1, offset=1)
    assert (len(page.items), page.total, page.limit, page.offset) == (1, 4, 1, 1)
    assert repository.search(["kavijar"]).items == []
    assert repository.search(["яйца"]).items == []


def test_search_ranks_by_relevance_then_package_price(
    price_csv: Callable[..., Path], database: Path, repository: PriceRepository
) -> None:
    rows = [
        "12;Šećer i med;ŠEĆER KRISTAL 1KG TM;SLOVA;8605002327784;kom;IDEA;16-11-2026;99.99;99.99;;;;20;VAZECI_CENOVNIK",
        "12;Šećer i med;ŠEĆER KRISTAL CRVENKA 50KG;CRVENKA;8606101115029;kg;IDEA;16-11-2026;3145.45;62.91;;;;20;VAZECI_CENOVNIK",
        "12;Šećer i med;SECER ZA KAFU ZA PONETI;LAVAZZA;2623103090730;kom;IDEA;16-11-2026;1.19;1.19;;;;20;VAZECI_CENOVNIK",
        "2;Pića;Nektar od banane 25% MK6 1l;Solevita;4335619190184;kom;IDEA;16-11-2026;130.99;130.99;;;;20;VAZECI_CENOVNIK",
        "3;Voće;Bio banane, rinfuz 1kg;RM;4335619068865;kom;IDEA;16-11-2026;229.99;229.99;;;;10;VAZECI_CENOVNIK",
    ]
    build_database(database, {"idea": price_csv("idea.csv", rows)})

    assert [r.name for r in repository.search(["banane"]).items] == ["Bio banane, rinfuz 1kg", "Nektar od banane 25% MK6 1l"]
    assert [r.price for r in repository.search(["secer"]).items] == [1.19, 99.99, 3145.45]


def test_search_folds_cyrillic_and_diacritics(
    price_csv: Callable[..., Path], database: Path, repository: PriceRepository
) -> None:
    rows = [
        "1;Млеко;МЛЕКО ЉУБИЧИЦА 2,8% 1Л;Њива;8600000000901;l;IDEA;16-11-2026;139.99;139.99;;;;20;VAZECI_CENOVNIK",
        "1;Mleko;ĐUVEČ Džem Šećer;;8600000000902;kom;IDEA;16-11-2026;99.99;99.99;;;;20;VAZECI_CENOVNIK",
    ]
    build_database(database, {"idea": price_csv("idea.csv", rows)})

    assert [r.ean for r in repository.search(["mleko ljubicica 2 8 njiva"]).items] == ["8600000000901"]
    assert [r.ean for r in repository.search(["djuvec dzem secer"]).items] == ["8600000000902"]


@pytest.mark.usefixtures("sample")
def test_compare_by_barcode_cleans_quotes_nul_and_zero_promo(repository: PriceRepository) -> None:
    offers = repository.compare_by_barcode("8600000000101").items

    assert [(o.store_formats, o.price, o.promo_price, o.diff_rsd, o.diff_pct) for o in offers] == [
        (["Mega Maxi"], 479.99, None, 0.0, 0.0),
        (["Maxi"], 499.99, None, 20.0, 4.17),
        (["UNIVEREXPORT - M"], 529.99, None, 50.0, 10.42),
    ]
    assert offers[2].name == "MASLAC LURPAK 82% 250G"
    assert offers[2].category == "ULJA I MASTI"
    assert [o.retailer for o in repository.compare_by_barcode("8600000000101", chains=["univerexport"]).items] == [
        "univerexport"
    ]


@pytest.mark.usefixtures("sample")
def test_price_history_combines_monthly_snapshots_and_current_list(repository: PriceRepository) -> None:
    history = repository.price_history("8600000000101", chains=["maxi"]).items

    assert [(p.store_formats, p.price_date.isoformat(), p.price, p.snapshot) for p in history] == [
        (["Maxi"], "2026-09-01", 449.99, "monthly"),
        (["Maxi"], "2026-10-01", 459.99, "monthly"),
        (["Maxi"], "2026-11-16", 499.99, "current"),
        (["Mega Maxi"], "2026-11-16", 479.99, "current"),
    ]
    assert repository.price_history("8600000000101", limit=1, offset=10).total == 5


@pytest.mark.usefixtures("sample")
def test_basket_costs_packages_per_store(repository: PriceRepository) -> None:
    items = [
        BasketItem(query="pileci file", quantity=1),
        BasketItem(query="maslac", quantity=1),
        BasketItem(query="jaja", quantity=2),
    ]

    options = repository.optimize_basket(items)

    assert [(o.store_format, o.total, o.missing) for o in options[:3]] == [
        ("Maxi", 1449.96, []),
        ("Lidl Srbija KD", 1539.96, []),
        ("UNIVEREXPORT - M", 1259.98, ["jaja"]),
    ]
    assert [(p.name, p.ean, p.price, p.quantity, p.cost) for p in options[0].picks] == [
        ("Pileci file 500g Sveze M", "8600000000103", 449.99, 1, 449.99),
        ("Maslac 82% Lurpak 250g", "8600000000101", 499.99, 1, 499.99),
        ("Jaja M 10/1", "8600000000104", 249.99, 2, 499.98),
    ]


@pytest.mark.usefixtures("sample")
def test_basket_filters_by_chain_and_ignores_items_without_latin_tokens(repository: PriceRepository) -> None:
    items = [BasketItem(query="яйца", quantity=10), BasketItem(query="maslac", quantity=1)]

    (option,) = repository.optimize_basket(items, chains=["lidl"])

    assert (option.store_format, [p.item for p in option.picks], option.missing) == ("Lidl Srbija KD", ["maslac"], [])


@pytest.mark.usefixtures("sample")
def test_basket_ignores_blank_barcode_without_latin_tokens(repository: PriceRepository) -> None:
    assert repository.optimize_basket([BasketItem(query="масло", ean=" ", quantity=1)]) == []


@pytest.mark.usefixtures("sample")
def test_basket_reports_missing_items_with_the_same_query(repository: PriceRepository) -> None:
    items = [
        BasketItem(query="maslac", ean="8600000000101", quantity=1),
        BasketItem(query="maslac", ean="4056489000001", quantity=1),
    ]

    lidl = next(o for o in repository.optimize_basket(items) if o.retailer == "lidl")

    assert (lidl.found, lidl.missing) == (1, ["maslac"])


@pytest.mark.usefixtures("sample")
def test_basket_by_barcode_buys_exactly_that_product(repository: PriceRepository) -> None:
    options = repository.optimize_basket([BasketItem(query="maslac Lurpak", ean="8600000000101", quantity=2)])

    assert [(o.store_format, o.total, o.picks[0].name) for o in options] == [
        ("Mega Maxi", 959.98, "Maslac 82% Lurpak 250g"),
        ("Maxi", 999.98, "Maslac 82% Lurpak 250g"),
        ("UNIVEREXPORT - M", 1059.98, "MASLAC LURPAK 82% 250G"),
    ]


@pytest.mark.usefixtures("sample")
def test_discounts_flag_regular_price_raised_before_promo(repository: PriceRepository) -> None:
    clearance, discount = repository.top_discounts(min_discount_pct=20).items

    assert (clearance.name, clearance.discount_pct, clearance.needs_verification) == (
        "KESA ZA PEČENJE 8/1 FRESH PACK", 91.23, True
    )
    assert (discount.name, discount.discount_pct, discount.needs_verification) == ("Maslac 82% Pilos 250g", 25.0, False)
    assert discount.promo_end == dt.date(2026, 11, 18)
    assert discount.regular_raised_before_promo
    assert discount.lowest_recent_price == 299.99
    assert repository.top_discounts(min_discount_pct=95).items == []


@pytest.mark.usefixtures("sample")
def test_catalog_lists_retailers_formats_and_categories(repository: PriceRepository) -> None:
    catalog = repository.catalog()

    assert [r.key for r in catalog.retailers] == ["lidl", "delhaize", "univerexport"]
    delhaize = catalog.retailers[1]
    assert (delhaize.store_formats, delhaize.products, delhaize.price_date) == (
        ["Maxi", "Mega Maxi"], 4, dt.date(2026, 11, 16)
    )
    assert catalog.retailers[2].products == 4
    assert catalog.categories == [
        "Mleko, mlečni i mešoviti proizvodi, jaja",
        "Sveže i prerađeno meso",
        "Slatki konditori i cerealije",
        "Ulja i masti",
        "Papirna i kuhinjska galanterija",
    ]


def test_queries_before_first_load_report_not_ready(repository: PriceRepository) -> None:
    with pytest.raises(DataNotReady):
        repository.catalog()
