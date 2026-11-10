"""Pitch names and tick math. 480 ticks per quarter note."""

import re

from .errors import OpenUtauError

TICKS_PER_BEAT = 480
_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_BASE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_PITCH = re.compile(r"^\s*([A-Ga-g])([#b♯♭]*)\s*(-?\d+)\s*$")


def to_midi(pitch) -> int:
    """MIDI number from an int, a numeric string, or a name like C4 (=60), A#3, Bb3, Cb4 (=59), C-1 (=0)."""
    if isinstance(pitch, bool):
        raise OpenUtauError(f"Invalid pitch: {pitch!r}", f"無効な音高です: {pitch!r}")
    if isinstance(pitch, (int, float)) and float(pitch).is_integer():
        n = int(pitch)
    elif isinstance(pitch, str) and re.fullmatch(r"\s*\d+\s*", pitch):
        n = int(pitch)
    else:
        m = _PITCH.match(str(pitch))
        if not m:
            raise OpenUtauError(
                f"Invalid pitch {pitch!r}: use a MIDI number or a name like C4, A#3, Bb3",
                f"無効な音高 {pitch!r}: MIDI番号か C4・A#3・Bb3 のような音名を指定してください",
            )
        letter, acc, octave = m.groups()
        n = (int(octave) + 1) * 12 + _BASE[letter.upper()]
        n += acc.count("#") + acc.count("♯") - acc.count("b") - acc.count("♭")
    if not 0 <= n <= 127:
        raise OpenUtauError(f"Pitch {pitch!r} is outside MIDI 0..127", f"音高 {pitch!r} が MIDI 0〜127 の範囲外です")
    return n


def to_name(midi: int) -> str:
    midi = to_midi(midi)
    return f"{_NAMES[midi % 12]}{midi // 12 - 1}"


def beats_to_ticks(beats: float) -> int:
    return round(beats * TICKS_PER_BEAT)


def ticks_to_beats(ticks: int) -> float:
    return ticks / TICKS_PER_BEAT


def repeat_last(values, count: int, name: str) -> list:
    """Expand a scalar or list to count items, repeating the last value."""
    if not isinstance(values, (list, tuple)):
        return [values] * count
    if not values:
        raise OpenUtauError(f"'{name}' must not be empty", f"'{name}' が空です")
    return [values[min(i, len(values) - 1)] for i in range(count)]


def layout_notes(lyrics: list[str], start: int, durations, tones) -> list[dict]:
    """Consecutive notes from start tick; durations/tones may be scalars or lists (last value repeats)."""
    durs = repeat_last(durations, len(lyrics), "durations")
    tns = repeat_last(tones, len(lyrics), "tones")
    notes, pos = [], int(start)
    for lyric, dur, tone in zip(lyrics, durs, tns):
        dur = int(dur)
        if dur <= 0:
            raise OpenUtauError(f"Duration must be positive: {dur}", f"長さは正の値にしてください: {dur}")
        notes.append({"position": pos, "duration": dur, "tone": to_midi(tone), "lyric": lyric})
        pos += dur
    return notes
