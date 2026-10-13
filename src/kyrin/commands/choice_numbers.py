"""Resolve an explicit spoken menu number, never a fuzzy numeric guess."""

import unicodedata

_ENGLISH = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19,
}
_PERSIAN = {
    "یک": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5,
    "شش": 6, "هفت": 7, "هشت": 8, "نه": 9, "ده": 10,
    "یازده": 11, "دوازده": 12, "سیزده": 13, "چهارده": 14,
    "پانزده": 15, "شانزده": 16, "هفده": 17, "هجده": 18,
    "نوزده": 19,
}
_ENGLISH_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_PERSIAN_TENS = {
    "بیست": 20, "سی": 30, "چهل": 40, "پنجاه": 50,
    "شصت": 60, "هفتاد": 70, "هشتاد": 80, "نود": 90,
}
_ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4,
    "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
    "ninth": 9, "tenth": 10,
    "اول": 1, "اولی": 1, "دوم": 2, "دومی": 2,
    "سوم": 3, "سومی": 3,
}


def _word_number(answer: str) -> int | None:
    if answer in _ORDINALS:
        return _ORDINALS[answer]
    if answer in _ENGLISH:
        return _ENGLISH[answer]
    if answer in _PERSIAN:
        return _PERSIAN[answer]
    if answer in _ENGLISH_TENS:
        return _ENGLISH_TENS[answer]
    if answer in _PERSIAN_TENS:
        return _PERSIAN_TENS[answer]
    english_parts = answer.replace("-", " ").split()
    if len(english_parts) == 2 and english_parts[0] in _ENGLISH_TENS:
        unit = _ENGLISH.get(english_parts[1])
        if unit is not None and unit < 10:
            return _ENGLISH_TENS[english_parts[0]] + unit
    persian_parts = answer.split(" و ")
    if len(persian_parts) == 2 and persian_parts[0] in _PERSIAN_TENS:
        unit = _PERSIAN.get(persian_parts[1])
        if unit is not None and unit < 10:
            return _PERSIAN_TENS[persian_parts[0]] + unit
    return None


def choice_index(phrase: str, count: int) -> int | None:
    """Return a zero-based choice only for a complete, in-range answer."""
    if count <= 0:
        return None
    answer = unicodedata.normalize("NFKC", phrase).casefold().strip()
    for prefix in ("number ", "option ", "شماره ", "گزینه "):
        if answer.startswith(prefix):
            answer = answer[len(prefix) :].strip()
            break
    if answer.isdecimal():
        try:
            number = int(answer)
        except (TypeError, ValueError):
            number = None
    else:
        number = _word_number(answer)
    return number - 1 if number is not None and 1 <= number <= count else None
