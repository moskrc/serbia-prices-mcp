from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from serbia_prices_mcp.loader import build_database
from serbia_prices_mcp.repository import PriceRepository

STANDARD_HEADER = (
    "KATEGORIJA;NAZIV KATEGORIJE;Naziv proizvoda;Robna marka;Barkod proizvoda;Jedinica mere;"
    "Naziv trgovca - formata;Datum cenovnika;Redovna cena;Cena po jedinici mere;Snižena cena;"
    "Datum početka sniženja;Datum kraja sniženja;Stopa PDV;VRSTA_CENOVNIKA"
)

DELHAIZE = [
    "15;Ulja i masti;Maslac 82% Lurpak 250g;Lurpak;8600000000101;kg;Maxi;16-11-2026;499.99;1999.96;;;;20;VAZECI_CENOVNIK",
    "15;Ulja i masti;Maslac 82% Lurpak 250g;Lurpak;8600000000101;kg;Mega Maxi;16-11-2026;479.99;1919.96;;;;20;VAZECI_CENOVNIK",
    "11;Slatki konditori i cerealije;Keks sa maslacem 200g;Plazma;8600000000102;kg;Maxi;16-11-2026;149.99;749.95;;;;20;VAZECI_CENOVNIK",
    "8;Sveže i prerađeno meso;Pileci file 500g Sveze M;Sveze M;8600000000103;kg;Maxi;16-11-2026;449.99;449.99;;;;10;VAZECI_CENOVNIK",
    "1;Mleko, mlečni i mešoviti proizvodi, jaja;Jaja M 10/1;Farma;8600000000104;kom;Maxi;16-11-2026;249.99;24.99;;;;10;VAZECI_CENOVNIK",
    "15;Ulja i masti;Maslac 82% Lurpak 250g;Lurpak;8600000000101;kg;Maxi;01-09-2026;449.99;1799.96;;;;20;MESECNI_PRESEK",
    "15;Ulja i masti;Maslac 82% Lurpak 250g;Lurpak;8600000000101;kg;Maxi;01-10-2026;459.99;1839.96;;;;20;MESECNI_PRESEK",
]
LIDL = [
    "8;Sveže i prerađeno meso;Pileći file MK12 ca. 1kg;Lidl;2000000000200;kg;Lidl Srbija KD;16-11-2026;779.99;779.99;;;;10;VAZECI_CENOVNIK",
    "15;Ulja i masti;Maslac 82% Pilos 250g;Pilos;4056489000001;g;Lidl Srbija KD;16-11-2026;399.99;1599.96;299.99;12-11-2026;18-11-2026;20;VAZECI_CENOVNIK",
    "1;Mleko, mlečni i mešoviti proizvodi, jaja;Jaja M 10 kom;Lidl;4056489000002;kom.;Lidl Srbija KD;16-11-2026;229.99;23.00;;;;10;VAZECI_CENOVNIK",
    "15;Ulja i masti;Maslac 82% Pilos 250g;Pilos;4056489000001;g;Lidl Srbija KD;01-10-2026;349.99;1399.96;;;;20;MESECNI_PRESEK",
    "20;Papirna i kuhinjska galanterija;KESA ZA PEČENJE 8/1 FRESH PACK;FRESH&PACK;3850334609861;kom.;Lidl Srbija KD;16-11-2026;57.00;57.00;5.00;12-11-2026;08-12-2026;20;VAZECI_CENOVNIK",
]
UNIVEREXPORT = [
    "﻿KATEGORIJA;NAZIV KATEGORIJE;Naziv proizvoda;Robna marka;Barkod proizvoda;Jedinica mere;Naziv trgovca – format;Datum cenovnika;Redovna cena;Cena po jedinici mere;Snižena cena;Datum početka sniženja;Datum kraja sniženja;Stopa PDV;VRSTA_CENOVNIKA",
    '15;"ULJA I MASTI";"MASLAC LURPAK 82% 250G";"LURPAK";"8600000000101";kg;UNIVEREXPORT - M;16-11-2026;529.99;2119.96;0;\x00;\x00;20;VAZECI_CENOVNIK',
    "8;SVEŽE I PRERAĐENO MESO;PILEĆI FILE RF;RM NIJE DEFINISANA;2000000000300;kg;UNIVEREXPORT - M;16-11-2026;729.99;729.99;0;;;10;VAZECI_CENOVNIK",
    "20;PAPIRNA I KUHINJSKA GALANTERIJA;KESE ZA ZAMRZIVAČ 5L FOKA;FOKA;8600000000011;Kom;UNIVEREXPORT - M;16-11-2026;117.65;117.65;0;;;20;VAZECI_CENOVNIK",
    "8;SVEŽE I PRERAĐENO MESO;PUREĆI FILE CCA 3KG VAKUUM;;2000000000500;kg;UNIVEREXPORT - M;16-11-2026;732.59;732.59;0;;;10;VAZECI_CENOVNIK",
    "8;SVEŽE I PRERAĐENO MESO;PILEĆI BATAK;;2000000000400;kg;UNIVEREXPORT - M;16-11-2026;;;0;;;10;VAZECI_CENOVNIK",
]


@pytest.fixture
def price_csv(tmp_path: Path) -> Callable[..., Path]:
    def write(name: str, rows: Sequence[str], *, bom: bool = False) -> Path:
        path = tmp_path / name
        text = ("﻿" if bom else "") + "\n".join([STANDARD_HEADER, *rows]) + "\n"
        path.write_bytes(text.encode("utf-8"))
        return path

    return write


@pytest.fixture
def database(tmp_path: Path) -> Path:
    return tmp_path / "data" / "prices.duckdb"


@pytest.fixture
def repository(database: Path) -> PriceRepository:
    return PriceRepository(database)


@pytest.fixture
def sample_sources(tmp_path: Path, price_csv: Callable[..., Path]) -> dict[str, Path | str]:
    univerexport = tmp_path / "univerexport.csv"
    univerexport.write_text("\n".join(UNIVEREXPORT) + "\n", encoding="utf-8")
    return {
        "lidl": price_csv("lidl.csv", LIDL),
        "delhaize": price_csv("delhaize.csv", DELHAIZE, bom=True),
        "univerexport": univerexport,
    }


@pytest.fixture
def sample(database: Path, sample_sources: dict[str, Path | str]) -> None:
    build_database(database, sample_sources)
