"""The text of a letter is a document of the page editor's `letter` set (CR-17
phase 7b, #2023). A test that needs a letter with some text gives it as the text
with markers Raakje writes; this turns it into the document the letter stores."""

from app.domains.newsletter.letter_markup import markup_to_document


def letter_doc(markup: str) -> dict:
    return markup_to_document(markup)
