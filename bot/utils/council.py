"""Разбор номера участника Совета из отображаемого имени (формат «О5-Число»)."""
from __future__ import annotations

import re
import unicodedata

_ROMAN_TO_INT = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
    "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIII": 13,
}

_COUNCIL_NUMBER_RE = re.compile(
    r"[OoОо][\s\-_–—:.．·]*\d+[\s\-_–—:.．·]+[OoОо]?[\s\-_–—:.．·]*"
    r"(\d{1,3}|IV|IX|X{0,2}I{0,3}|V?I{1,3})"
)

_DASHES = ("\u2013", "\u2014", "\u2212", "\u2015")


def parse_council_number(display_name: str) -> int | None:
    """Возвращает номер из ника вида «О5-12» / «O5.IV»; None, если не найден."""
    if not display_name:
        return None
    name = unicodedata.normalize("NFKC", display_name)
    for dash in _DASHES:
        name = name.replace(dash, "-")
    m = _COUNCIL_NUMBER_RE.search(name)
    if not m:
        return None
    token = m.group(1)
    if token.isdigit():
        return int(token)
    return _ROMAN_TO_INT.get(token.upper())
