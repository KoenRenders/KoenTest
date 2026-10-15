"""The attributes of the `membership` domain: every business column of its tables (CR-33).

Generated once from the ORM and the rules of the inventory, then kept by hand like
`codes.py`. `label` is filled where a screen shows the datum; the comment after the
classification names the rule of the inventory that decided it.
"""

from app.kernel.attributes import AiExposure, Attribute

ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="membership.membership.year",
        columns=("membership.memberships.year",),
        label="Lidmaatschapsjaar",
        name_en="Year",
        help="Het jaar waarover een lidmaatschap gaat.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="membership.membership.is_active",
        columns=("membership.memberships.is_active",),
        label=None,
        name_en="Is active",
        help="The is active of the membership.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="membership.membership.valid_from",
        columns=("membership.memberships.valid_from",),
        label=None,
        name_en="Valid from",
        help="The valid from of the membership.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="membership.membership.valid_to",
        columns=("membership.memberships.valid_to",),
        label=None,
        name_en="Valid to",
        help="The valid to of the membership.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
)
