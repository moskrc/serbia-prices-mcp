import re
import unicodedata

_TRANSLATION = str.maketrans({
    "đ": "dj", "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ђ": "dj", "е": "e", "ж": "z", "з": "z",
    "и": "i", "ј": "j", "к": "k", "л": "l", "љ": "lj", "м": "m", "н": "n", "њ": "nj", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "ћ": "c", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "c", "џ": "dz", "ш": "s",
})
_WHITESPACE = re.compile(r"\s+")


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    lowered = text.lower().translate(_TRANSLATION)
    decomposed = unicodedata.normalize("NFD", lowered)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return _WHITESPACE.sub(" ", stripped).strip()
