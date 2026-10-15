"""The minutes of a meeting point are a document of the page editor's `notes` set
(CR-17 phase 7, #2023). Tests that need a note on a point build it here."""


def note(*paragraphs: str, italic: bool = False) -> dict:
    """A document of plain paragraphs (each with its text in italics when asked)."""
    marks = [{"type": "italic"}] if italic else []
    return {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text, **({"marks": marks} if marks else {})}],
            }
            for text in paragraphs
        ],
    }
