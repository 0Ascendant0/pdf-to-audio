"""Save edited chapters as EPUB, PDF or plain text."""
import re
import uuid
from html import escape
from pathlib import Path


def pretty(name: str) -> str:
    """'003_chapter_one' -> 'Chapter One'."""
    name = re.sub(r"^\d+_", "", name).replace("_", " ").strip()
    return name.title() if name else "Section"


def _paras(text):
    return [re.sub(r"\s*\n\s*", " ", p.strip())
            for p in re.split(r"\n\s*\n", text) if p.strip()]


def export_txt(chapters, path, title=""):
    body = "\n\n\n".join(text.strip() for _, text in chapters)
    Path(path).write_text(body + "\n", encoding="utf-8")


def export_epub(chapters, path, title="Edited book"):
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier(f"book2audio-{uuid.uuid4()}")
    book.set_title(title)
    book.set_language("en")

    items = []
    for i, (name, text) in enumerate(chapters, 1):
        item = epub.EpubHtml(title=pretty(name), file_name=f"chap_{i:03d}.xhtml", lang="en")
        item.content = "".join(f"<p>{escape(p)}</p>" for p in _paras(text)) or "<p></p>"
        book.add_item(item)
        items.append(item)

    book.toc = tuple(items)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + items
    epub.write_epub(str(path), book)


def export_pdf(chapters, path, title=""):
    """Reflowed A4 PDF (the original page layout is not preserved)."""
    import pymupdf as fitz

    css = "body{font-family:serif;font-size:11pt;line-height:1.4} p{margin:0 0 8pt 0}"
    parts = []
    for i, (_, text) in enumerate(chapters):
        style = ' style="page-break-before: always;"' if i else ""
        paras = "".join(f"<p>{escape(p)}</p>" for p in _paras(text)) or "<p></p>"
        parts.append(f"<div{style}>{paras}</div>")

    story = fitz.Story(html="".join(parts), user_css=css)
    writer = fitz.DocumentWriter(str(path))
    mediabox = fitz.paper_rect("a4")
    where = mediabox + (54, 54, -54, -54)
    more = True
    while more:
        dev = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
