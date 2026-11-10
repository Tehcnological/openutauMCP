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


def parse_melody(melody: str) -> list[tuple[int | None, int]]:
    """'A4:1 A4:1 B4:2 r:1/2 C5' -> [(midi or None for a rest, ticks)]; length is in quarter-note beats
    (default 1; decimals or fractions like 1/2, 3/2)."""
    out = []
    for tok in melody.replace(",", " ").replace("|", " ").split():
        pitch, _, length = tok.partition(":")
        try:
            num, _, den = (length or "1").partition("/")
            beats = float(num) / float(den or 1)
        except ValueError:
            beats = -1
        if beats <= 0:
            raise OpenUtauError(f"Bad melody length in {tok!r} (use e.g. A4:1, C5:1/2, r:2)",
                                f"メロディの長さが不正です: {tok!r}（例 A4:1、C5:1/2、r:2）")
        out.append((None if pitch.lower() in ("r", "rest", "-") else to_midi(pitch), beats_to_ticks(beats)))
    if not out:
        raise OpenUtauError("Empty melody", "メロディが空です")
    return out


def melody_notes(melody: str, lyrics: list[str] | None, start: int) -> list[dict]:
    """Notes from a melody string; lyrics (one per sounding note) must match the note count when given."""
    events = parse_melody(melody)
    sounding = sum(p is not None for p, _ in events)
    if lyrics is not None and len(lyrics) != sounding:
        raise OpenUtauError(
            f"Melody has {sounding} notes but the lyrics split into {len(lyrics)}: {lyrics}",
            f"メロディは {sounding} 音ですが、歌詞は {len(lyrics)} 個に分割されました: {lyrics}")
    notes, pos, it = [], int(start), iter(lyrics or [])
    for pitch, ticks in events:
        if pitch is not None:
            notes.append({"position": pos, "duration": ticks, "tone": pitch, "lyric": next(it, "a")})
        pos += ticks
    return notes


def fitted_length(notes: list[dict], bar_ticks: int) -> int:
    """Part length that ends on the first bar line at or after the last note (at least one bar)."""
    end = max((n["position"] + n["duration"] for n in notes), default=0)
    return max(1, -(-end // bar_ticks)) * bar_ticks


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
