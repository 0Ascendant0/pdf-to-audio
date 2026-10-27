"""Find / replace helpers (pure Python, no GUI). Used by the editor and the CLI."""
import re


def compile_pattern(find, match_case=False, whole_word=False, use_regex=False):
    """Build a compiled regex from the user's search options.

    Raises ValueError with a readable message on empty or invalid input.
    """
    if not find:
        raise ValueError("Enter text to find")
    expr = find if use_regex else re.escape(find)
    if whole_word:
        expr = rf"\b(?:{expr})\b"
    flags = 0 if match_case else re.IGNORECASE
    if use_regex:
        flags |= re.MULTILINE
    try:
        return re.compile(expr, flags)
    except re.error as e:
        raise ValueError(f"Invalid regex: {e}")


def find_next(pat, text, pos=0):
    """First non-empty match at or after pos, or None."""
    while pos <= len(text):
        m = pat.search(text, pos)
        if m is None:
            return None
        if m.end() > m.start():
            return m
        pos = m.end() + 1
    return None


def count_matches(pat, text):
    return sum(1 for m in pat.finditer(text) if m.end() > m.start())


def replace_all(pat, text, repl, use_regex=False):
    """Return (new_text, replacement_count).

    In regex mode the replacement may use groups (\\1, \\g<name>) and escapes (\\n).
    In plain mode the replacement is taken literally.
    """
    count = 0

    def sub(m):
        nonlocal count
        if m.end() == m.start():
            return ""
        count += 1
        return m.expand(repl) if use_regex else repl

    try:
        new = pat.sub(sub, text)
    except (re.error, IndexError) as e:
        raise ValueError(f"Bad replacement: {e}")
    return new, count


def expand_one(pat, text, start, end, repl, use_regex=False):
    """Replacement string for the single match at text[start:end], or None
    if the pattern no longer matches exactly that span."""
    m = pat.match(text, start)
    if m is None or m.end() != end:
        return None
    try:
        return m.expand(repl) if use_regex else repl
    except (re.error, IndexError) as e:
        raise ValueError(f"Bad replacement: {e}")
