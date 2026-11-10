"""Chunking: every piece fits the embedding window, keeps its heading and overlaps its neighbour."""
from app.ingest.chunking import split_text


def test_consecutive_chunks_share_the_short_parts_that_fit_the_overlap():
    text = "\n\n".join(f"Item {i}: curto." for i in range(12))
    chunks = split_text(text, chunk_size=60, chunk_overlap=20)
    assert len(chunks) > 1
    for a, b in zip(chunks, chunks[1:]):
        assert a.split("\n\n")[-1] == b.split("\n\n")[0]
    assert all(len(c) <= 60 for c in chunks)


def test_long_paragraph_is_cut_at_sentence_ends_and_nothing_is_lost():
    sentence = "Esta é uma frase longa sobre a oficina da Escola Bike Anjo. "
    text = "## Oficina\n\n" + sentence * 40 + "\n\n## Outra\n\ncurto"
    chunks = split_text(text, chunk_size=512, chunk_overlap=64)
    assert all(len(c) <= 512 for c in chunks)
    body = [c for c in chunks if c.startswith("## Oficina")]
    assert len(body) > 1, "every piece of the section keeps the heading"
    joined = " ".join(c.replace("## Oficina\n\n", "") for c in body)
    assert joined.count("Escola Bike Anjo") == 40


def test_word_longer_than_the_chunk_is_still_cut():
    chunks = split_text("x" * 1300, chunk_size=512, chunk_overlap=0)
    assert [len(c) for c in chunks] == [512, 512, 276]


def test_short_markdown_sections_stay_whole():
    text = "# Sobre: A\n\nUm.\n\n## B\n\nDois."
    assert split_text(text) == ["# Sobre: A\n\nUm.", "## B\n\nDois."]
