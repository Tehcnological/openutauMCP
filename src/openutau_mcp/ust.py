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


def read(path: str) -> dict:
    """Returns {"tempo": bpm, "project_name": str, "notes": [{position, duration, tone, lyric}]} (rests dropped)."""
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
                notes.append({"position": pos, "duration": length, "tone": int(kv.get("NoteNum", "60")), "lyric": lyric})
            pos += length
    return {"tempo": tempo, "project_name": name, "notes": notes}


def to_ustx(path: str, singer: str | None = None, phonemizer: str | None = None) -> dict:
    data = read(path)
    project = ustx.new_project(bpm=data["tempo"], singer=singer, phonemizer=phonemizer,
                               name=data["project_name"] or os.path.splitext(os.path.basename(path))[0])
    end = max((n["position"] + n["duration"] for n in data["notes"]), default=0)
    p = ustx.add_voice_part(project, 0, 0, max(end, 1920), os.path.splitext(os.path.basename(path))[0])
    ustx.add_notes(project["voice_parts"][p], data["notes"])
    return project


def write(path: str, notes: list[dict], tempo: float, project_name: str = "", encoding: str = "shift_jis") -> int:
    """Write notes (part-relative, sorted) as a .ust. Gaps become R rests. Returns number of note blocks."""
    blocks, pos = [], 0
    for n in sorted(notes, key=lambda n: n["position"]):
        if n["position"] < pos:
            continue  # overlapping note: UTAU cannot express it
        if n["position"] > pos:
            blocks.append((n["position"] - pos, "R", 60))
        blocks.append((n["duration"], n.get("lyric", "a"), n["tone"]))
        pos = n["position"] + n["duration"]
    lines = ["[#VERSION]", "UST Version1.2"]
    if encoding.lower().replace("-", "_") not in ("shift_jis", "sjis", "cp932"):
        lines.append(f"Charset={encoding}")
    lines += ["[#SETTING]", f"Tempo={tempo:g}", "Tracks=1", f"ProjectName={project_name}", "VoiceDir=", "OutFile=",
              "CacheDir=", "Tool1=wavtool.exe", "Tool2=resampler.exe", "Mode2=True"]
    for i, (length, lyric, tone) in enumerate(blocks):
        lines += [f"[#{i:04d}]", f"Length={length}", f"Lyric={lyric}", f"NoteNum={tone}", "PreUtterance=",
                  "Intensity=100", "Modulation=0"]
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
