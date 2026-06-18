"""De privacy-pagina bevat de spraakinvoer-sectie na de seed-migraties (#282, migr. 061)."""
from app.models.cms import CmsPage


def test_privacy_page_has_stt_section(db_session):
    page = db_session.query(CmsPage).filter(CmsPage.slug == "privacy").first()
    assert page is not None, "privacy-pagina ontbreekt (049 niet gedraaid?)"
    content = page.content or ""
    assert "Spraakinvoer" in content
    assert "Mistral AI" in content  # de EU-verwerker-vermelding
    assert "Vivaldi" in content     # de browser-lijst (Firefox/Vivaldi/Opera)
    assert "Brave" not in content   # Brave is eruit gehaald (niet-Europees)
