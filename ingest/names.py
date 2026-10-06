"""Player name normalization (docs/schema-proposal.md §1, aliases), shared by the builder and
merge_candidates.py, so a name matches the same way wherever it's compared."""

import re
import unicodedata


def normalize(name):
    """A name as aliases are matched: no team tag ('Pink | Guichabou' -> 'Guichabou'), accents
    folded, lowercase, letters and digits only."""
    name = unicodedata.normalize("NFKD", (name or "").split("|")[-1])
    return re.sub(r"[\W_]+", "", "".join(c for c in name if not unicodedata.combining(c)).casefold())
