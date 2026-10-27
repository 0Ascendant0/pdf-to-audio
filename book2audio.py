#!/usr/bin/env python3
"""Core engine: read PDF / EPUB, optionally find-and-replace, and convert to audio
locally with Kokoro-82M (CPU-friendly).

CLI:
    python book2audio.py mybook.epub -o out/ --voice af_heart --speed 0.95
    python book2audio.py mybook.pdf --replace "Dr." "Doctor" --replace "NASA" "nassa"
GUI:
    python app.py

Output goes to <out>/<book name>/. Resumable: a chapter is skipped only if its
audio exists AND its text, voice and speed are unchanged since last time.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import editlib

SR = 24000  # Kokoro's output sample rate


# ---------- text cleaning ----------
def clean(text: str) -> str:
    text = re.sub(r"^\s*\d+\s*$", "", text, flags=re.M)      # bare page numbers
    text = re.sub(r"-\n(\w)", r"\1", text)                    # de-hyphenate line breaks
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)              # single newline -> space
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------- readers: return [(chapter_name, text), ...] ----------
def read_pdf(path: Path, pages_per_chapter: int = 10):
    import pymupdf as fitz

    doc = fitz.open(path)
    chapters = []
    for start in range(0, len(doc), pages_per_chapter):
        pages = [doc[i].get_text() for i in range(start, min(start + pages_per_chapter, len(doc)))]
        text = clean("\n\n".join(pages))
        if text:
            chapters.append((f"pages_{start + 1:04d}", text))
    return chapters


def read_epub(path: Path):
    import ebooklib
    from bs4 import BeautifulSoup
    from ebooklib import epub

    book = epub.read_epub(str(path))
    chapters = []
    for idref, _ in book.spine:
        item = book.get_item_with_id(idref)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        soup = BeautifulSoup(item.get_content(), "html.parser")
        blocks = soup.find_all(["h1", "h2", "h3", "p"])
        text = clean("\n\n".join(b.get_text(" ", strip=True) for b in blocks))
        if len(text) > 200:  # skip covers, copyright pages, etc.
            chapters.append((f"{len(chapters) + 1:03d}_{Path(item.get_name()).stem}", text))
    return chapters


def load_chapters(path):
    """Read a .pdf or .epub into [(chapter_name, text), ...]."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        chapters = read_pdf(path)
    elif ext == ".epub":
        chapters = read_epub(path)
    else:
        raise ValueError("Only .pdf and .epub are supported")
    if not chapters:
        raise ValueError("No readable text found (scanned PDF? run OCR first)")
    return chapters


# ---------- synthesis ----------
def synthesize(pipe, text, voice, speed, on_chars=None, cancel=None):
    """Returns a float32 array, or None if empty/cancelled."""
    import numpy as np

    para_pause = np.zeros(int(SR * 0.7), dtype=np.float32)
    parts = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if cancel and cancel():
            return None
        for _, _, audio in pipe(para, voice=voice, speed=speed):
            parts.append(audio.numpy() if hasattr(audio, "numpy") else np.asarray(audio))
        parts.append(para_pause)
        if on_chars:
            on_chars(len(para))
    return np.concatenate(parts) if parts else None


def _signature(text, voice, speed):
    return hashlib.sha1(f"{voice}|{speed}|{text}".encode("utf-8")).hexdigest()


def convert(input_path, out_dir, voice="af_heart", speed=1.0,
            log=print, progress=None, cancel=None, chapters=None):
    """Convert a book to audio. Returns True if finished, False if cancelled.

    chapters:  optional [(name, text), ...] to use instead of re-reading the file
               (this is how edited text from the GUI is passed in).
    progress:  optional callback progress(fraction 0..1)
    cancel:    optional callback cancel() -> bool
    """
    import soundfile as sf

    input_path = Path(input_path)
    if chapters is None:
        log("Reading book...")
        chapters = load_chapters(input_path)
    if not chapters:
        raise ValueError("Nothing to convert")
    total = sum(len(t) for _, t in chapters) or 1
    done = 0

    log("Loading voice model (first run downloads ~300 MB)...")
    from kokoro import KPipeline

    pipe = KPipeline(lang_code=voice[0])  # a = American, b = British

    book_dir = Path(out_dir) / input_path.stem
    book_dir.mkdir(parents=True, exist_ok=True)
    have_ffmpeg = shutil.which("ffmpeg") is not None

    manifest_file = book_dir / ".book2audio.json"
    try:
        manifest = json.loads(manifest_file.read_text())
    except (OSError, ValueError):
        manifest = {}

    def bump(n):
        nonlocal done
        done += n
        if progress:
            progress(min(done / total, 1.0))

    for name, text in chapters:
        if cancel and cancel():
            log("Cancelled.")
            return False
        final = book_dir / (f"{name}.mp3" if have_ffmpeg else f"{name}.wav")
        sig = _signature(text, voice, speed)
        if final.exists() and manifest.get(final.name) == sig:
            log(f"Skipping {name} (already done)")
            bump(len(text))
            continue
        log(f"Synthesizing {name} ({len(text):,} chars)...")
        audio = synthesize(pipe, text, voice, speed, on_chars=bump, cancel=cancel)
        if audio is None:
            if cancel and cancel():
                log("Cancelled.")
                return False
            continue
        wav = book_dir / f"{name}.wav"
        sf.write(wav, audio, SR)
        if have_ffmpeg:
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "64k", str(final)],
                check=True,
            )
            wav.unlink()
        manifest[final.name] = sig
        manifest_file.write_text(json.dumps(manifest, indent=1))
        log(f"Saved {final.name}")

    log(f"Done -> {book_dir}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("audio_out"))
    ap.add_argument("--voice", default="af_heart", help="e.g. af_heart, af_bella, am_michael, bf_emma")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--replace", nargs=2, action="append", default=[], metavar=("FIND", "REPLACE"),
                    help="find-and-replace applied before conversion (repeatable)")
    ap.add_argument("--regex", action="store_true", help="treat --replace FIND as a regex")
    ap.add_argument("--match-case", action="store_true", help="case-sensitive --replace")
    args = ap.parse_args()

    chapters = load_chapters(args.input)
    for find, repl in args.replace:
        pat = editlib.compile_pattern(find, args.match_case, False, args.regex)
        total = 0
        new = []
        for name, text in chapters:
            text, n = editlib.replace_all(pat, text, repl, args.regex)
            total += n
            new.append((name, text))
        chapters = new
        print(f"replaced {total}x: {find!r} -> {repl!r}")

    convert(args.input, args.out, args.voice, args.speed, chapters=chapters)


if __name__ == "__main__":
    main()
