"""Tags with a tree in the media library (CR-15 phase 1, #1470; C6 tests 9 and 11).

Measured on the service, the one way in:

- **the tree** (test 9): a tag with a child tag and two tagged pictures is a
  tree; a picture with two tags appears under both, and under the tag above them;
- **tags are repeatable** (test 11): two tags on one picture are two rows; the
  same tag twice is refused by the primary key, and asking the service twice
  changes nothing;
- **deleting** refuses a tag with a child tag or a tag in use, naming how many;
  an empty tag goes;
- **the tree stays a tree**: moving a tag under itself or one of its own
  descendants is refused, and two tags of one name under one parent — also at
  the top, where a plain UNIQUE would let them in — are refused;
- **the migration's starting tags**: "Logo's", "Sponsors" and "Pagina's" carry
  the pictures of their kind, and activity photos get no tag.

Proven red against master `4d2d641f`: the module does not import there —
`create_tag` and `MediaTag` do not exist.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.domains.media.api import (
    MediaAssetTag,
    MediaFout,
    create_tag,
    delete_tag,
    list_media_with_tag,
    move_tag,
    rename_tag,
    set_asset_tags,
    tag_asset,
    tag_tree,
    tags_of_assets,
    untag_asset,
)
from app.domains.media.models import MediaAsset


def _asset(db, *, kind="page_image", title="foto", activity_id=None):
    asset = MediaAsset(
        kind=kind,
        activity_id=activity_id,
        title=title,
        sort_order=0,
        is_active=True,
        content_type="image/jpeg",
        byte_size=10,
        width=10,
        height=10,
        data=b"x",
        thumbnail=b"y",
    )
    db.add(asset)
    db.commit()
    return asset


def _node(tree, name):
    """The node named `name`, anywhere in the tree."""
    for node in tree:
        if node.name == name:
            return node
        found = _node(node.children, name)
        if found:
            return found
    return None


def test_a_tag_with_a_child_and_two_pictures_is_a_tree(db_session):
    """C6 test 9: a picture with two tags appears under both, and under the tag above."""
    jeugd_parent = create_tag(db_session, "Jeugd")
    kamp = create_tag(db_session, "Kamp", parent_id=jeugd_parent.id)
    sint = create_tag(db_session, "Sint")
    beide = _asset(db_session, title="kamp met de Sint")
    alleen_kamp = _asset(db_session, title="tenten")
    tag_asset(db_session, beide.id, kamp.id)
    tag_asset(db_session, beide.id, sint.id)
    tag_asset(db_session, alleen_kamp.id, kamp.id)

    tree = tag_tree(db_session)

    jeugd = _node(tree, "Jeugd")
    assert [c.name for c in jeugd.children] == ["Kamp"], "a tree, not a flat list"
    assert _node(tree, "Kamp").pictures == 2
    assert jeugd.pictures == 2, "the parent counts the pictures below it, each once"
    assert _node(tree, "Sint").pictures == 1
    under_jeugd = {a["id"] for a in list_media_with_tag(db_session, jeugd.id)}
    under_sint = {a["id"] for a in list_media_with_tag(db_session, sint.id)}
    assert under_jeugd == {beide.id, alleen_kamp.id}
    assert under_sint == {beide.id}, "the picture with two tags is under both"


def test_tags_are_repeatable_and_the_same_tag_twice_is_refused(db_session):
    """C6 test 11."""
    a = create_tag(db_session, "Logo's")
    b = create_tag(db_session, "Sponsors")
    asset = _asset(db_session)

    tag_asset(db_session, asset.id, a.id)
    tag_asset(db_session, asset.id, b.id)
    tag_asset(db_session, asset.id, a.id)  # asked twice: nothing changes

    rows = db_session.query(MediaAssetTag).filter(MediaAssetTag.asset_id == asset.id).count()
    assert rows == 2, "two tags are two rows; asking twice adds none"
    assert sorted(tags_of_assets(db_session, [asset.id])[asset.id]) == sorted([a.id, b.id])

    savepoint = db_session.begin_nested()
    with pytest.raises(IntegrityError):
        db_session.add(MediaAssetTag(asset_id=asset.id, tag_id=a.id))
        db_session.flush()
    savepoint.rollback()


def test_a_tag_with_a_child_or_in_use_is_not_deleted(db_session):
    parent = create_tag(db_session, "Pagina's")
    child = create_tag(db_session, "Jeugd", parent_id=parent.id)
    in_use = create_tag(db_session, "Sint")
    for _ in range(2):
        tag_asset(db_session, _asset(db_session).id, in_use.id)
    empty = create_tag(db_session, "Leeg")

    with pytest.raises(MediaFout, match="1 ondertag"):
        delete_tag(db_session, parent.id)
    with pytest.raises(MediaFout, match="2 foto"):
        delete_tag(db_session, in_use.id)

    delete_tag(db_session, empty.id)
    delete_tag(db_session, child.id)
    names = [n.name for n in tag_tree(db_session)]
    assert "Leeg" not in names and _node(tag_tree(db_session), "Jeugd") is None


def test_untag_and_set_the_exact_tags(db_session):
    a, b, c = (create_tag(db_session, n) for n in ("A", "B", "C"))
    asset = _asset(db_session)
    set_asset_tags(db_session, asset.id, [a.id, b.id])
    set_asset_tags(db_session, asset.id, [b.id, c.id])
    assert sorted(tags_of_assets(db_session, [asset.id])[asset.id]) == sorted([b.id, c.id])
    untag_asset(db_session, asset.id, b.id)
    assert tags_of_assets(db_session, [asset.id])[asset.id] == [c.id]


def test_the_tree_stays_a_tree_and_names_are_unique_per_parent(db_session):
    top = create_tag(db_session, "Logo's")
    mid = create_tag(db_session, "Sponsors", parent_id=top.id)
    low = create_tag(db_session, "Goud", parent_id=mid.id)

    with pytest.raises(MediaFout, match="onder zichzelf"):
        move_tag(db_session, top.id, low.id)
    with pytest.raises(MediaFout, match="onder zichzelf"):
        move_tag(db_session, top.id, top.id)
    with pytest.raises(MediaFout, match="bestaat hier al"):
        create_tag(db_session, "Logo's")
    with pytest.raises(MediaFout, match="bestaat hier al"):
        create_tag(db_session, "Sponsors", parent_id=top.id)
    create_tag(db_session, "Sponsors")  # another parent (the top): allowed

    rename_tag(db_session, low.id, "Zilver")
    move_tag(db_session, low.id, None)
    assert _node(tag_tree(db_session), "Zilver").parent_id is None


def test_two_top_level_tags_of_one_name_are_refused_by_the_key(db_session):
    """A plain UNIQUE would let them in: two NULL parents count as different.
    Migration 186 makes the key NULLS NOT DISTINCT."""
    create_tag(db_session, "Logo's")
    savepoint = db_session.begin_nested()
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO media.tags (parent_id, name, tenant_id) "
                "SELECT NULL, 'Logo''s', tenant_id FROM media.tags WHERE name = 'Logo''s'"
            )
        )
    savepoint.rollback()


def _migration_186():
    import importlib.util
    from pathlib import Path

    path = next(
        (Path(__file__).resolve().parents[4] / "alembic" / "versions").glob(
            "186_*_media_tags_with_a_tree.py"
        )
    )
    spec = importlib.util.spec_from_file_location("migration_186", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_starting_tags_gather_their_kinds_and_leave_activities_alone(db_session):
    """Koen, 2 October 2026: "Logo's", "Sponsors" and "Pagina's" carry the rows of
    their kind; activity photos get no tag (a derived branch). Run twice: the
    same result — the seed is idempotent."""
    logo = _asset(db_session, kind="tenant_logo")
    sponsors = [_asset(db_session, kind="sponsor") for _ in range(2)]
    page = _asset(db_session, kind="page_image")
    photo = _asset(db_session, kind="activity_photo")
    seed = _migration_186().seed_starting_tags

    seed(db_session.connection())
    seed(db_session.connection())
    db_session.commit()

    tree = tag_tree(db_session)
    assert {n.name: n.pictures for n in tree} == {"Logo's": 1, "Sponsors": 2, "Pagina's": 1}
    tags = tags_of_assets(db_session, [logo.id, page.id, photo.id, *(s.id for s in sponsors)])
    assert tags[photo.id] == [], "an activity photo gets no tag"
    assert all(len(tags[a.id]) == 1 for a in (logo, page, *sponsors))
