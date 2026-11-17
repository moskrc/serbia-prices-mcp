from typing import Literal

from pydantic import BaseModel

RetailerKey = Literal[
    "lidl", "delhaize", "idea", "univerexport", "gomex", "aman", "metro", "dm", "aroma", "beltorg", "veropoulos",
]


class Retailer(BaseModel, frozen=True):
    key: RetailerKey
    name: str
    organization_id: str


RETAILERS: tuple[Retailer, ...] = (
    Retailer(key="lidl", name="Lidl", organization_id="68f0ece19e69a823f887080b"),
    Retailer(key="delhaize", name="Delhaize (Maxi, Mega Maxi, Shop&Go)", organization_id="68f1f7d6420ab5ccb306665f"),
    Retailer(key="idea", name="Idea / Mercator / Roda", organization_id="68f5f21cc197b0aed4a4d930"),
    Retailer(key="univerexport", name="Univerexport", organization_id="68f0ddca9e69a823f887080a"),
    Retailer(key="gomex", name="Gomex", organization_id="68f76c79f9a700f329626af0"),
    Retailer(key="aman", name="Aman", organization_id="68f0bd87323b9450f4f7c868"),
    Retailer(key="metro", name="Metro Cash&Carry", organization_id="6a969722f7c49d15c159cf17"),
    Retailer(key="dm", name="dm drogerie markt", organization_id="69ca35d75d679fa197ab2471"),
    Retailer(key="aroma", name="Aroma", organization_id="68f5e3b3b6d8d54345cce9cd"),
    Retailer(key="beltorg", name="Beltorg (Svetofor)", organization_id="68f73bc7f240807aaff49939"),
    Retailer(key="veropoulos", name="Veropoulos", organization_id="68f0c2c6e2564c5a9a88d1ed"),
)
