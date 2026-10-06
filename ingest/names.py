"""Name normalization (docs/schema-proposal.md §1, aliases), shared by the builder and
merge_candidates.py, so a name matches the same way wherever it's compared."""

import re
import unicodedata


def fold(text):
    """Lowercase, with accents folded ('Machèèèèté' -> 'macheeeete')."""
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def normalize(name):
    """A player name as aliases are matched: no team tag ('Pink | Guichabou' -> 'Guichabou'), accents
    folded, lowercase, letters and digits only."""
    return re.sub(r"[\W_]+", "", fold((name or "").split("|")[-1]))


def normalize_words(text):
    """An event alias as it's matched: accents folded, lowercase, words split on anything but letters
    and digits, one space between them ('BCX  2022!' -> 'bcx 2022')."""
    return " ".join(word for word in re.split(r"[\W_]+", fold(text)) if word)
