"""Read/write OpenUtau .ustx project files (YAML) without OpenUtau running.

Layout follows OpenUtau.Core/Format/USTx.cs and Ustx/*.cs (snake_case keys). Missing default
expressions are added back by OpenUtau when it loads the file.
"""

import os
import re

import yaml

from .errors import OpenUtauError
from .music import to_midi


class _Loader(yaml.SafeLoader):
    """YAML 1.1 would read option names like on/off/yes/no as booleans; keep them as strings."""


_Loader.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag != "tag:yaml.org,2002:bool"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF")
)


class _Dumper(yaml.SafeDumper):
    pass


DEFAULT_PHONEMIZER = "OpenUtau.Core.DefaultPhonemizer"
USTX_VERSION = "0.10"


def default_vibrato() -> dict:
    return {"length": 0, "period": 175, "depth": 25, "in": 10, "out": 10, "shift": 0, "drift": 0, "vol_link": 0}


def make_note(position: int, duration: int, tone, lyric: str = "a") -> dict:
    """Same shape as UProject.CreateNote: two default portamento points (-40 and +40 ms)."""
    if int(position) < 0 or int(duration) <= 0:
        raise OpenUtauError(
            f"Bad note position/duration: {position}/{duration}", f"音符の位置・長さが不正です: {position}/{duration}"
        )
    return {
        "position": int(position),
        "duration": int(duration),
        "tone": to_midi(tone),
        "lyric": str(lyric),
        "pitch": {"data": [{"x": -40, "y": 0, "shape": "io"}, {"x": 40, "y": 0, "shape": "io"}], "snap_first": True},
        "vibrato": default_vibrato(),
        "tuning": 0,
        "phoneme_expressions": [],
        "phoneme_overrides": [],
    }


def make_track(name: str, singer: str | None = None, phonemizer: str | None = None) -> dict:
    t = {
        "phonemizer": phonemizer or DEFAULT_PHONEMIZER,
        "renderer_settings": {},
        "track_name": name,
        "track_color": "Blue",
        "mute": False,
        "solo": False,
        "volume": 0,
        "pan": 0,
        "track_expressions": [],
        "voice_color_names": [""],
    }
    if singer:
        t = {"singer": singer, **t}
    return t


def new_project(bpm: float = 120, singer: str | None = None, phonemizer: str | None = None, name: str = "New Project") -> dict:
    if not 10 <= float(bpm) <= 1000:
        raise OpenUtauError("BPM must be 10..1000", "BPM は 10〜1000 にしてください")
    return {
        "name": name,
        "comment": "",
        "output_dir": "Vocal",
        "cache_dir": "UCache",
        "ustx_version": USTX_VERSION,
        "expressions": {},
        "exp_selectors": ["dyn", "pitd", "clr", "eng", "vel", "vol", "atk", "dec", "gen", "bre"],
        "exp_primary": 0,
        "exp_secondary": 1,
        "key": 0,
        "time_signatures": [{"bar_position": 0, "beat_per_bar": 4, "beat_unit": 4}],
        "tempos": [{"position": 0, "bpm": bpm}],
        "tracks": [make_track("Track1", singer, phonemizer)],
        "voice_parts": [],
        "wave_parts": [],
    }


def load(path: str) -> dict:
    if not os.path.isfile(path):
        raise OpenUtauError(f"File not found: {path}", f"ファイルが見つかりません: {path}")
    with open(path, encoding="utf-8-sig") as f:
        data = yaml.load(f, Loader=_Loader)
    if not isinstance(data, dict) or "tracks" not in data:
        raise OpenUtauError(f"Not a .ustx project: {path}", f".ustx プロジェクトではありません: {path}")
    data.setdefault("voice_parts", [])
    data.setdefault("wave_parts", [])
    return data


def save(project: dict, path: str) -> None:
    if not path.lower().endswith(".ustx"):
        raise OpenUtauError("Path must end with .ustx", "パスは .ustx で終わる必要があります")
    for part in project.get("voice_parts") or []:
        part["notes"] = sorted(part.get("notes") or [], key=lambda n: n["position"])
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    text = yaml.dump(project, Dumper=_Dumper, allow_unicode=True, sort_keys=False, default_flow_style=False)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def voice_part(project: dict, index: int) -> dict:
    parts = project.get("voice_parts") or []
    if not 0 <= index < len(parts):
        raise OpenUtauError(
            f"Voice part {index} does not exist ({len(parts)} parts)", f"ボイスパート {index} は存在しません（{len(parts)} 個）"
        )
    part = parts[index]
    part["notes"] = sorted(part.get("notes") or [], key=lambda n: n["position"])
    return part


def track(project: dict, index: int) -> dict:
    tracks = project["tracks"]
    if not 0 <= index < len(tracks):
        raise OpenUtauError(
            f"Track {index} does not exist ({len(tracks)} tracks)", f"トラック {index} は存在しません（{len(tracks)} 個）"
        )
    return tracks[index]


def add_track(project: dict, name: str | None = None, singer: str | None = None, phonemizer: str | None = None) -> int:
    project["tracks"].append(make_track(name or f"Track{len(project['tracks']) + 1}", singer, phonemizer))
    return len(project["tracks"]) - 1


def add_voice_part(project: dict, track_no: int, position: int = 0, duration: int = 7680, name: str = "New Part") -> int:
    track(project, track_no)
    if position < 0 or duration <= 0:
        raise OpenUtauError("Bad part position/duration", "パートの位置・長さが不正です")
    project["voice_parts"].append(
        {"duration": int(duration), "name": name, "comment": "", "track_no": track_no, "position": int(position),
         "notes": [], "curves": [], "masked_curves": []}
    )
    return len(project["voice_parts"]) - 1


def add_notes(part: dict, notes: list[dict]) -> list[int]:
    """notes: dicts with position, duration, tone, lyric. Grows the part if needed; returns new indices."""
    created = [make_note(n["position"], n["duration"], n["tone"], n.get("lyric", "a")) for n in notes]
    part["notes"] = sorted((part.get("notes") or []) + created, key=lambda n: n["position"])
    end = max(n["position"] + n["duration"] for n in part["notes"]) if part["notes"] else 0
    part["duration"] = max(int(part.get("duration", 0)), end)
    ids = {id(n) for n in created}
    return [i for i, n in enumerate(part["notes"]) if id(n) in ids]


VIBRATO_KEYS = ("length", "period", "depth", "in", "out", "shift", "drift")
_VIB_RANGE = {"length": (0, 100), "period": (5, 500), "depth": (5, 200), "in": (0, 100), "out": (0, 100),
              "shift": (0, 100), "drift": (-100, 100)}


def set_vibrato(note: dict, **values) -> None:
    vib = note.setdefault("vibrato", default_vibrato())
    for k, v in values.items():
        if v is None:
            continue
        lo, hi = _VIB_RANGE[k]
        vib[k] = max(lo, min(hi, float(v)))
    # fade in + fade out may not exceed 100% (mirrors UVibrato)
    if vib["in"] + vib["out"] > 100:
        if values.get("out") is not None:
            vib["in"] = 100 - vib["out"]
        else:
            vib["out"] = 100 - vib["in"]


def edit_note(note: dict, edit: dict) -> None:
    if edit.get("position") is not None:
        if int(edit["position"]) < 0:
            raise OpenUtauError("Position must be >= 0", "位置は 0 以上にしてください")
        note["position"] = int(edit["position"])
    if edit.get("duration") is not None:
        if int(edit["duration"]) <= 0:
            raise OpenUtauError("Duration must be positive", "長さは正の値にしてください")
        note["duration"] = int(edit["duration"])
    if edit.get("tone") is not None:
        note["tone"] = to_midi(edit["tone"])
    if edit.get("lyric") is not None:
        note["lyric"] = str(edit["lyric"])
    if edit.get("tuning") is not None:
        note["tuning"] = int(edit["tuning"])
    if edit.get("vibrato"):
        set_vibrato(note, **{k: edit["vibrato"].get(k) for k in VIBRATO_KEYS})


def note_info(i: int, n: dict) -> dict:
    return {"index": i, "position": n["position"], "duration": n["duration"], "tone": n["tone"],
            "lyric": n.get("lyric", ""), "tuning": n.get("tuning", 0),
            "vibrato": {k: (n.get("vibrato") or default_vibrato()).get(k) for k in VIBRATO_KEYS}}


def summary(project: dict, path: str | None = None) -> dict:
    return {
        "file_path": path,
        "name": project.get("name"),
        "ustx_version": project.get("ustx_version"),
        "key": project.get("key", 0),
        "tempos": project.get("tempos"),
        "time_signatures": project.get("time_signatures"),
        "tracks": [
            {"track": i, "name": t.get("track_name"), "singer": t.get("singer"), "phonemizer": t.get("phonemizer"),
             "renderer": (t.get("renderer_settings") or {}).get("renderer"), "volume": t.get("volume", 0),
             "pan": t.get("pan", 0), "mute": t.get("mute", False), "solo": t.get("solo", False)}
            for i, t in enumerate(project["tracks"])
        ],
        "voice_parts": [
            {"part": i, "name": p.get("name"), "track": p.get("track_no"), "position": p.get("position", 0),
             "duration": p.get("duration", 0), "note_count": len(p.get("notes") or [])}
            for i, p in enumerate(project.get("voice_parts") or [])
        ],
        "wave_part_count": len(project.get("wave_parts") or []),
    }


def set_tempo(project: dict, bpm: float, tick: int = 0) -> None:
    if not 10 <= float(bpm) <= 1000:
        raise OpenUtauError("BPM must be 10..1000", "BPM は 10〜1000 にしてください")
    tempos = [t for t in project.get("tempos") or [] if t["position"] != int(tick)]
    tempos.append({"position": int(tick), "bpm": bpm})
    project["tempos"] = sorted(tempos, key=lambda t: t["position"])
    if project["tempos"][0]["position"] != 0:
        project["tempos"].insert(0, {"position": 0, "bpm": 120})

