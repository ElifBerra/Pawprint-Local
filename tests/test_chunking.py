"""Tests for document splitting.

No models are needed here — chunking is pure text processing, so these run in
milliseconds and can be run on every change.
"""

import pytest

from src import chunking

DOC = """# Nutrition and Feeding

Intro paragraph before any second-level heading.

## Water

Fresh water should always be available at all times for every animal.

## Foods that are dangerous

Chocolate contains theobromine. Grapes can cause kidney failure in dogs.
"""


def test_empty_text_produces_nothing():
    assert chunking.split_document("", "a.md") == []
    assert chunking.split_document("   \n\n  ", "a.md") == []


def test_source_and_index_are_set():
    chunks = chunking.split_document(DOC, "nutrition.md")
    assert chunks
    assert all(c.source == "nutrition.md" for c in chunks)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_embedding_is_not_set_by_chunking():
    # Ingestion fills this in; chunking must not invent one.
    chunks = chunking.split_document(DOC, "nutrition.md")
    assert all(c.embedding is None for c in chunks)


def test_chunks_never_merge_across_headings():
    # This is the rule that fixed the chocolate/kidney-disease contamination:
    # no chunk may contain text from both sections.
    chunks = chunking.split_document(DOC, "nutrition.md")
    for chunk in chunks:
        has_water = "Fresh water" in chunk.content
        has_food = "theobromine" in chunk.content
        assert not (has_water and has_food), chunk.content


def test_each_chunk_carries_its_heading_trail():
    chunks = chunking.split_document(DOC, "nutrition.md")
    water = next(c for c in chunks if "Fresh water" in c.content)
    danger = next(c for c in chunks if "theobromine" in c.content)

    assert water.content.startswith("Nutrition and Feeding > Water")
    assert danger.content.startswith("Nutrition and Feeding > Foods that are dangerous")


def test_text_before_any_heading_keeps_the_document_title():
    chunks = chunking.split_document(DOC, "nutrition.md")
    intro = next(c for c in chunks if "Intro paragraph" in c.content)
    assert intro.content.startswith("Nutrition and Feeding")


def test_heading_trail_pops_back_to_the_right_level():
    doc = "# Top\n\n## A\n\nalpha text\n\n## B\n\nbeta text\n"
    chunks = chunking.split_document(doc, "x.md")
    alpha = next(c for c in chunks if "alpha" in c.content)
    beta = next(c for c in chunks if "beta" in c.content)

    # B must not be nested under A.
    assert alpha.content.startswith("Top > A")
    assert beta.content.startswith("Top > B")


def test_long_section_is_split_into_several_chunks():
    body = " ".join(f"word{i}" for i in range(500))
    doc = f"# Title\n\n## Section\n\n{body}\n"
    chunks = chunking.split_document(doc, "x.md", chunk_size=100, overlap=10)
    assert len(chunks) >= 5


def test_overlap_repeats_words_between_consecutive_chunks():
    paragraphs = "\n\n".join(" ".join(f"w{i}_{j}" for j in range(40)) for i in range(10))
    doc = f"# Title\n\n## Section\n\n{paragraphs}\n"
    chunks = chunking.split_document(doc, "x.md", chunk_size=80, overlap=20)
    assert len(chunks) > 1

    first_words = set(chunks[0].content.split())
    second_words = set(chunks[1].content.split())
    shared = first_words & second_words
    # The heading trail is shared by construction; require real body overlap.
    body_overlap = {w for w in shared if w.startswith("w")}
    assert body_overlap


def test_overlap_is_capped_so_chunking_always_advances():
    # An overlap >= chunk_size would otherwise loop forever.
    body = " ".join(f"word{i}" for i in range(300))
    doc = f"# Title\n\n{body}\n"
    chunks = chunking.split_document(doc, "x.md", chunk_size=50, overlap=999)
    assert 1 < len(chunks) < 100


def test_paragraph_longer_than_chunk_size_is_windowed():
    body = " ".join(f"word{i}" for i in range(250))
    doc = f"# Title\n\n{body}\n"
    chunks = chunking.split_document(doc, "x.md", chunk_size=100, overlap=0)
    assert len(chunks) >= 3


def test_split_sections_returns_trail_and_body():
    sections = chunking.split_sections(DOC)
    trails = [trail for trail, _ in sections]
    assert "Nutrition and Feeding > Water" in trails
    assert "Nutrition and Feeding > Foods that are dangerous" in trails


@pytest.mark.parametrize("text", ["no headings at all, just a sentence", "# Only a heading\n"])
def test_degenerate_documents_do_not_crash(text):
    chunking.split_document(text, "x.md")
