# Book → Audio

Edit **PDF** and **EPUB** books, then turn them into natural-sounding audio. Fully offline, on a normal CPU. No GPU, no API keys, no cloud.

Powered by [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M), a small open-weight TTS model with surprisingly human voices.

## Features

**Editing**
- Open a PDF or EPUB and edit its text chapter by chapter
- Find and replace with *match case*, *whole word* and *regex* options (regex replacements can use groups like `\1`)
- Find Next searches across the whole book and wraps around
- Replace one, replace all in the chapter, or replace all in the book
- Edited chapters are marked with a dot; revert any chapter to its original text
- Export the edited book as **EPUB**, **PDF** or **TXT**

**Conversion**
- Converts the edited text (or the original file) to audio, one file per chapter
- Cleans text before reading: removes bare page numbers, fixes hyphenated line breaks, joins wrapped lines
- Longer pauses between paragraphs for natural pacing
- Resumable: a chapter is skipped only if its audio exists and its text, voice and speed are unchanged
- American and British voices, adjustable speed
- Cancel any time; completed chapters are kept

**Interface**
- Black, square-cornered desktop GUI (customtkinter) plus a command-line mode

## Install

Requires Python 3.10 to 3.12.

1. Install system tools:
   - **espeak-ng** (required by Kokoro)
     - Linux: `sudo apt install espeak-ng python3-tk`
     - macOS: `brew install espeak-ng`
     - Windows: install from the [espeak-ng releases](https://github.com/espeak-ng/espeak-ng/releases)
   - **ffmpeg** (optional, gives smaller MP3 files instead of WAV)
2. Install Python packages:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

The first conversion downloads the voice model (about 300 MB).

## Usage

### GUI

```bash
python app.py
```

**EDIT tab:** *Open Book*, then edit the text or use Find / Replace (`Ctrl+F` jumps to the find box).
Pick a format and press *Export* to save the edited book.

**CONVERT tab:** pick an output folder, voice and speed, then press *Convert*.
If the selected file is the book open in the EDIT tab, your edits are used automatically.
Audio is saved to `<output folder>/<book name>/`.

### Command line

```bash
python book2audio.py mybook.epub -o out/
python book2audio.py paper.pdf -o out/ --voice af_bella --speed 0.95

# find-and-replace before converting (repeatable), handy for pronunciation fixes
python book2audio.py mybook.epub --replace "Dr." "Doctor" --replace "SQL" "sequel"
python book2audio.py mybook.epub --regex --replace "\bw/\b" "with"
```

## Voices

| Prefix | Accent | Examples |
|--------|--------|----------|
| `af_`, `am_` | American (female / male) | `af_heart`, `af_bella`, `am_michael` |
| `bf_`, `bm_` | British (female / male) | `bf_emma`, `bm_george` |

## Notes and limitations

- **Editing works on extracted text, not the original layout.** A PDF's page design cannot be edited in place, so exports are clean reflowed documents: EPUB keeps chapters and a table of contents, PDF is a plain A4 layout. Images, tables and fonts from the original are not carried over.
- Scanned PDFs have no text layer. Run them through OCR first (for example `ocrmypdf in.pdf out.pdf`).
- PDF headers and footers are only partly removed (bare page numbers are stripped). Use Find / Replace with a regex to clean up the rest.
- CPU synthesis takes time: a full book can take a few hours.

## Development

```bash
pip install pytest
python -m pytest tests
```

## Project structure

```
book2audio/
├── app.py            # GUI (CONVERT and EDIT tabs)
├── book2audio.py     # reading, conversion engine, CLI
├── editlib.py        # find / replace logic (no GUI)
├── exporters.py      # save edited text as EPUB / PDF / TXT
├── tests/
├── requirements.txt
└── README.md
```

## Roadmap

- Smarter PDF header/footer removal
- Single `.m4b` audiobook with chapter markers
- Chapter titles from the EPUB table of contents
- Per-book pronunciation dictionary

## License

Add a license of your choice (MIT is a common default).
Kokoro-82M is released under the Apache 2.0 license.
