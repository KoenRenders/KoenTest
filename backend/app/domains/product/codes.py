"""The code list the product domain owns (CR-21): the life cycle of an article.

`product_status` is the whole article's state (Q74): Concept → In verkoop →
Afgevoerd, and never back to Concept. One state for the whole article, none per
size.
"""

from app.domains.product.models import ProductStatus, ProductStatusCode, ProductStatusLabel
from app.kernel.codes import CodeList, CodeSeed

PRODUCT_STATUS_CODES = (
    CodeSeed(code="CONCEPT", nl="Concept", en="Concept", sort_order=10),
    CodeSeed(code="ON_SALE", nl="In verkoop", en="On sale", sort_order=20),
    CodeSeed(code="DISCONTINUED", nl="Afgevoerd", en="Discontinued", sort_order=30),
)

PRODUCT_STATUS = CodeList(
    name="product_status",
    schema="product",
    codes=ProductStatusCode,
    labels=ProductStatusLabel,
    enum=ProductStatus,
    fk_from=("product.products.status",),
)
