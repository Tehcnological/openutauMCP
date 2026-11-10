"""Split lyric text into one token per note (Japanese: one mora per note; English: one word per note)."""

import re
import unicodedata

from .errors import OpenUtauError

_KANA = re.compile(r"[぀-ヿㇰ-ㇿｦ-ﾟ]")
_KANJI = re.compile(r"[㐀-䶿一-鿿豈-﫿々〆]")
_SMALL = set("ゃゅょぁぃぅぇぉゎャュョァィゥェォヮ")
_OWN = set("っッー")
_EXTENDERS = {"+", "+~", "+*"}


def detect_language(text: str) -> str:
    return "ja" if _KANA.search(text) or _KANJI.search(text) else "en"


def _kanji_to_hiragana(text: str, warnings: list[str]) -> str:
    if not _KANJI.search(text):
        return text
    try:
        import pykakasi
    except ImportError:
        warnings.append(
            "Kanji kept as-is: install pykakasi (pip install pykakasi) to convert kanji to hiragana / "
            "漢字はそのまま残しました: pykakasi をインストールするとひらがなに変換できます"
        )
        return text
    out = []
    for item in pykakasi.kakasi().convert(text):
        orig = item["orig"]
        out.append(item["hira"] if _KANJI.search(orig) else orig)
    return "".join(out)


def _split_japanese(text: str, warnings: list[str]) -> list[str]:
    text = unicodedata.normalize("NFKC", text)  # half-width kana → full-width, full-width ASCII → ASCII
    text = _kanji_to_hiragana(text, warnings)
    tokens: list[str] = []
    prev_kana = False
    word = ""
    for ch in text + " ":
        if ch.isascii() and (ch.isalnum() or ch in "'+~*"):
            word += ch  # romaji: one space-separated word per note
            prev_kana = False
            continue
        if word:
            tokens.append(word.lower() if not word.startswith("+") else word)
            word = ""
        if ch in _SMALL and prev_kana and ch not in _OWN:
            tokens[-1] += ch
        elif ch in _OWN or _KANA.match(ch):
            tokens.append(ch)
            prev_kana = ch not in _OWN
        elif _KANJI.match(ch):
            tokens.append(ch)  # only reached without pykakasi
            prev_kana = False
        else:
            prev_kana = False  # spaces, punctuation (、。！？…「」 etc.) are dropped
    return tokens


def _split_english(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in text.split():
        if raw in _EXTENDERS:
            tokens.append(raw)
            continue
        word = re.sub(r"^[^\w']+|[^\w']+$", "", raw).lower()
        if not word.strip("'"):
            continue
        syllables = [s for s in word.split("-") if s]
        if not syllables:
            continue
        tokens.append("".join(syllables))
        tokens.extend(["+"] * (len(syllables) - 1))
    return tokens


def split_lyrics(text: str, language: str = "auto") -> tuple[list[str], list[str], str]:
    """Returns (tokens, warnings, language used)."""
    lang = (language or "auto").lower()
    if lang == "auto":
        lang = detect_language(text)
    if lang not in ("ja", "en"):
        raise OpenUtauError(
            f"Unknown language {language!r}: use auto, ja or en",
            f"不明な言語 {language!r}: auto・ja・en のいずれかを指定してください",
        )
    warnings: list[str] = []
    tokens = _split_japanese(text, warnings) if lang == "ja" else _split_english(text)
    return tokens, warnings, lang
