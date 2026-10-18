"""The code list the pricing domain owns (CR-21): who a price is for.

Two kinds of price from the start (Q5): the regular price and the member price,
both with their own date. A second price is a row with a type, not a column
`member_price` (B3a).
"""

from app.domains.pricing.models import PriceType, PriceTypeCode, PriceTypeLabel
from app.kernel.codes import CodeList, CodeSeed

PRICE_TYPE_CODES = (
    CodeSeed(code="REGULAR", nl="Prijs", en="Price", sort_order=10),
    CodeSeed(code="MEMBER", nl="Ledenprijs", en="Member price", sort_order=20),
)

PRICE_TYPE = CodeList(
    name="price_type",
    schema="pricing",
    codes=PriceTypeCode,
    labels=PriceTypeLabel,
    enum=PriceType,
    fk_from=("pricing.prices.price_type",),
)
