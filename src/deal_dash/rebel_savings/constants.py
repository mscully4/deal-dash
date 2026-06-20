from enum import StrEnum


class Retailer(StrEnum):
    HOMEDEPOT = "homedepot"
    LOWES = "lowes"
    WALMART = "walmart"
    WALGREENS = "walgreens"
    TRACTORSUPPLY = "tractorsupply"


RETAILER_META: dict[str, tuple[str, str]] = {
    Retailer.HOMEDEPOT: ("hd", "home-depot"),
    Retailer.LOWES: ("lowes", "lowes"),
    Retailer.WALMART: ("walmart", "walmart"),
    Retailer.WALGREENS: ("walgreens", "walgreens"),
    Retailer.TRACTORSUPPLY: ("tsc", "tractor-supply"),
}

RETAILERS = list(RETAILER_META.keys())

DEFAULT_ZIP_CODE = "78681"
DEFAULT_RADIUS = 15.0
DEFAULT_DAYS = 2
