"""Classic UTAU .ust import/export (Shift_JIS by default; a Charset= line overrides)."""

import os
import re

from . import ustx
from .errors import OpenUtauError


def _detect_encoding(raw: bytes) -> str:
    for line in raw.splitlines()[:10]:
        m = re.match(rb"\s*Charset=(\S+)", line)
        if m:
            return m.group(1).decode("ascii", "replace")
    return "shift_jis"


def _num(s: str) -> float:
    try:
        return float(s) if s.strip() else 0.0  # UTAU leaves 0 fields empty
    except ValueError:
        return 0.0


_SHAPES = {"r": "o", "s": "l", "j": "i"}  # UTAU PBM -> OpenUtau PitchPointShape (blank = io)
_SHAPES_BACK = {"o": "r", "l": "s", "i": "j"}


def _pitch(kv: dict) -> list[dict] | None:
    """Mode2 portamento (PBS/PBW/PBY/PBM) as .ustx pitch points, x = ms from note start, y = 1/10 semitone.
    Same rules as OpenUtau's UstNote.ParsePitchBend, starting from the default two points."""
    pbs, pbw, pby, pbm = (kv.get(k, "").strip() for k in ("PBS", "PBW", "PBY", "PBM"))
    if not (pbs or pbw or pby or pbm):
        return None
    pts = [{"x": -40.0, "y": 0.0, "shape": "io"}, {"x": 40.0, "y": 0.0, "shape": "io"}]
    if pbs:
        a = pbs.split(";" if ";" in pbs else ",")
        pts[0] = {"x": _num(a[0]), "y": _num(a[1]) if len(a) > 1 else 0.0, "shape": "io"}
    w = [_num(v) for v in pbw.split(",")] if pbw else []
    y = [_num(v) for v in pby.split(",")] if pby else []
    x = pts[0]["x"]
    if len(w) == 1 and not y:  # widths only
        pts[1]["x"] = x + w[0]
    elif len(y) == 1 and not w:  # heights only
        pts[1]["y"] = y[0]
    elif w or y:
        y += [0.0] * (len(w) - len(y))
        pts = pts[:1]
        for wi, yi in zip(w, y):
            x += wi
            pts.append({"x": x, "y": yi, "shape": "io"})
    for i, m in enumerate(pbm.split(",") if pbm else []):
        if i < len(pts):
            pts[i]["shape"] = _SHAPES.get(m, "io")
    return pts if len(pts) > 1 else None


def read(path: str) -> dict:
    """Returns {"tempo": bpm, "project_name": str, "notes": [{position, duration, tone, lyric, pitch?, vibrato?}]}
    (rests dropped). pitch = .ustx pitch points from PBS/PBW/PBY/PBM; vibrato = .ustx vibrato from VBR."""
    if not os.path.isfile(path):
        raise OpenUtauError(f"File not found: {path}", f"ファイルが見つかりません: {path}")
    with open(path, "rb") as f:
        raw = f.read()
    enc = _detect_encoding(raw)
    try:
        text = raw.decode(enc)
    except (LookupError, UnicodeDecodeError) as e:
        raise OpenUtauError(f"Cannot decode {path} as {enc}: {e}", f"{path} を {enc} として読めません: {e}") from e
    blocks: list[tuple[str, dict]] = []
    for line in text.splitlines():
        line = line.strip()
        if re.fullmatch(r"\[#[^\]]+\]", line):
            blocks.append((line, {}))
        elif "=" in line and blocks:
            k, v = line.split("=", 1)
            blocks[-1][1][k.strip()] = v.strip()
    tempo, name, notes, pos = 120.0, "", [], 0
    for header, kv in blocks:
        if header == "[#SETTING]":
            tempo = float(kv.get("Tempo", tempo) or tempo)
            name = kv.get("ProjectName", "")
        elif re.fullmatch(r"\[#\d+\]", header):
            length = int(float(kv.get("Length", "480")))
            lyric = kv.get("Lyric", "")
            if lyric.lower() not in ("r", ""):
                note = {"position": pos, "duration": length, "tone": int(kv.get("NoteNum", "60")), "lyric": lyric}
                pitch = _pitch(kv)
                if pitch:
                    note["pitch"] = pitch
                if "VBR" in kv:  # length %, cycle ms, depth cents, fade-in %, fade-out %, phase %, height % (-> drift)
                    note["vibrato"] = dict(zip(ustx.VIBRATO_KEYS, (_num(v) for v in kv["VBR"].split(","))))
                notes.append(note)
            pos += length
    return {"tempo": tempo, "project_name": name, "notes": notes}


def to_ustx(path: str, singer: str | None = None, phonemizer: str | None = None) -> dict:
    data = read(path)
    project = ustx.new_project(bpm=data["tempo"], singer=singer, phonemizer=phonemizer,
                               name=data["project_name"] or os.path.splitext(os.path.basename(path))[0])
    end = max((n["position"] + n["duration"] for n in data["notes"]), default=0)
    p = ustx.add_voice_part(project, 0, 0, max(end, 1920), os.path.splitext(os.path.basename(path))[0])
    part = project["voice_parts"][p]
    ustx.add_notes(part, data["notes"])
    prev_end = None
    for src, note in zip(data["notes"], part["notes"]):  # both sorted by position
        if "pitch" in src:
            note["pitch"]["data"] = src["pitch"]
        if "vibrato" in src:
            ustx.set_vibrato(note, **src["vibrato"])
        # as OpenUtau's importer: a note after a rest does not snap its first pitch point to the previous note
        if prev_end is None or note["position"] > prev_end:
            note["pitch"]["snap_first"] = False
        prev_end = note["position"] + note["duration"]
    return project


def _tuning_lines(note: dict) -> list[str]:
    """PBS/PBW/PBY/PBM and VBR lines, written the way OpenUtau's UstNote does."""
    lines, g = [], lambda v: f"{float(v):g}"
    pts = (note.get("pitch") or {}).get("data") or []
    if len(pts) >= 2:
        lines += [f"PBS={g(pts[0]['x'])};{g(pts[0]['y'])}",
                  "PBW=" + ",".join(g(b["x"] - a["x"]) for a, b in zip(pts, pts[1:])),
                  "PBY=" + ",".join(g(p["y"]) for p in pts[1:]),
                  "PBM=" + ",".join(_SHAPES_BACK.get(p.get("shape", "io"), "") for p in pts)]
    vib = note.get("vibrato") or {}
    if vib.get("length", 0) > 0:
        lines.append("VBR=" + ",".join(g(vib.get(k, 0)) for k in ustx.VIBRATO_KEYS))
    return lines


def write(path: str, notes: list[dict], tempo: float, project_name: str = "", encoding: str = "shift_jis") -> int:
    """Write notes (part-relative, sorted) as a .ust. Gaps become R rests. Returns number of note blocks."""
    if not path.lower().endswith(".ust"):  # lyrics are caller text: never write them under another file type
        raise OpenUtauError("Path must end with .ust", "パスは .ust で終わる必要があります")
    one_line = lambda s: " ".join(str(s).splitlines())  # a line break in a name or lyric would start a new UST line
    blocks, pos = [], 0
    for n in sorted(notes, key=lambda n: n["position"]):
        if n["position"] < pos:
            continue  # overlapping note: UTAU cannot express it
        if n["position"] > pos:
            blocks.append((n["position"] - pos, "R", 60, None))
        blocks.append((n["duration"], n.get("lyric", "a"), n["tone"], n))
        pos = n["position"] + n["duration"]
    lines = ["[#VERSION]", "UST Version1.2"]
    if encoding.lower().replace("-", "_") not in ("shift_jis", "sjis", "cp932"):
        lines.append(f"Charset={encoding}")
    lines += ["[#SETTING]", f"Tempo={tempo:g}", "Tracks=1", f"ProjectName={one_line(project_name)}", "VoiceDir=", "OutFile=",
              "CacheDir=", "Tool1=wavtool.exe", "Tool2=resampler.exe", "Mode2=True"]
    for i, (length, lyric, tone, note) in enumerate(blocks):
        lines += [f"[#{i:04d}]", f"Length={length}", f"Lyric={one_line(lyric)}", f"NoteNum={tone}", "PreUtterance=",
                  "Intensity=100", "Modulation=0"]
        if note:
            lines += _tuning_lines(note)
    lines.append("[#TRACKEND]")
    try:
        data = ("\r\n".join(lines) + "\r\n").encode(encoding)
    except UnicodeEncodeError as e:
        raise OpenUtauError(
            f"A lyric cannot be written in {encoding}; use encoding='utf-8'",
            f"歌詞の一部が {encoding} で保存できません。encoding='utf-8' を指定してください",
        ) from e
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return len(blocks)
