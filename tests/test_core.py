import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import book2audio
import editlib
import exporters

LOREM = "The quick brown fox jumps over the lazy dog. " * 8


def test_plain_replace_is_literal_and_case_insensitive():
    pat = editlib.compile_pattern("a.b")
    new, n = editlib.replace_all(pat, "A.B a.b aXb", r"\1", use_regex=False)
    assert n == 2 and new == r"\1 \1 aXb"


def test_whole_word():
    pat = editlib.compile_pattern("cat", whole_word=True)
    new, n = editlib.replace_all(pat, "cat concat cat.", "dog")
    assert n == 2 and new == "dog concat dog."


def test_match_case():
    pat = editlib.compile_pattern("Cat", match_case=True)
    assert editlib.count_matches(pat, "Cat cat CAT") == 1


def test_regex_groups_and_escapes():
    pat = editlib.compile_pattern(r"(\w+)@(\w+)", use_regex=True)
    new, n = editlib.replace_all(pat, "bob@site", r"\2 \1\n", use_regex=True)
    assert n == 1 and new == "site bob\n"


def test_errors():
    with pytest.raises(ValueError):
        editlib.compile_pattern("")
    with pytest.raises(ValueError):
        editlib.compile_pattern("(", use_regex=True)
    pat = editlib.compile_pattern("a", use_regex=True)
    with pytest.raises(ValueError):
        editlib.replace_all(pat, "a", r"\5", use_regex=True)


def test_empty_matches_ignored():
    pat = editlib.compile_pattern("x*", use_regex=True)
    assert editlib.find_next(pat, "abc") is None
    assert editlib.count_matches(pat, "abc xx") == 1


def test_expand_one():
    pat = editlib.compile_pattern("fox")
    assert editlib.expand_one(pat, "a fox", 2, 5, "cat") == "cat"
    assert editlib.expand_one(pat, "a fox", 0, 3, "cat") is None


CHAPTERS = [("001_intro", "Intro\n\n" + LOREM), ("002_end", "The end.\n\n" + LOREM)]


def test_epub_roundtrip(tmp_path):
    out = tmp_path / "b.epub"
    exporters.export_epub(CHAPTERS, out, title="T")
    got = book2audio.load_chapters(out)
    assert len(got) == 2
    assert "quick brown fox" in got[0][1]


def test_pdf_roundtrip(tmp_path):
    out = tmp_path / "b.pdf"
    exporters.export_pdf(CHAPTERS, out)
    got = book2audio.load_chapters(out)
    joined = " ".join(t for _, t in got)
    assert "quick brown fox" in joined and "The end." in joined


def test_txt(tmp_path):
    out = tmp_path / "b.txt"
    exporters.export_txt(CHAPTERS, out)
    assert "The end." in out.read_text()
