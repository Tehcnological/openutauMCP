"""Compare a synth vocal project with the original recording it covers, before spending more time on tuning.

  reference_check.py separate MIX.wav OUTDIR          vocals.wav + no_vocals.wav with Demucs (its own venv)
  reference_check.py notes REF (--ustx P.ustx [--part 0] | --midi P.mid [--track N]) [--offset S]
      (a) notes the singer sings a steady 1-2.5 semitones off the written note (octave errors ignored):
          usually a dropped melisma or a wrong transcription; it can dip below the note, not only rise
      (b) long notes (>= dotted 8th) the singer releases before 80 % and stays silent until 40 ticks before the
          next note (that last bit is the next consonant)
  reference_check.py balance REF --vocal LEAD.wav --backing BACKING.wav (--ustx ... | --midi ...) [--offset S]
          [--render-offset S] [--sections verse:1-8,chorus:9-16]
      (c) vocal-vs-backing level per section, render stems against the original (Demucs vocals vs no_vocals)
  reference_check.py loudness RENDER.wav [--normalize OUT.wav]
      (d) integrated LUFS and true peak; --normalize writes a -14 LUFS / -1 dBTP listening copy (ffmpeg loudnorm)
  reference_check.py --self-check

REF is the original full mix (separated with Demucs into OUTDIR next to it, reused on later runs) or an already
separated vocal given as --ref-vocal V.wav (balance also needs --ref-backing B.wav). --offset = seconds into the
reference where project tick 0 falls; --render-offset = the same for the render stems (0 for an OpenUtau export).
Bars are counted from 1 at tick 0. Needs librosa + soundfile (see SKILL.md §5b), pyyaml for --ustx, mido for --midi;
Demucs (optional) runs from its own venv: --demucs-python, default %LOCALAPPDATA%\\demucs\\venv\\Scripts\\python.exe.
Engine-agnostic: works for any project whose lead notes can be written as .ustx or MIDI.
"""
import argparse
import os
import re
import subprocess
import sys

import numpy as np

SR, HOP = 22050, 256
NAMES = "C C# D D# E F F# G G# A A# B".split()
LONG, GUARD = 360, 40  # ticks: dotted 8th; the next note's consonant may start this early


# ---------- pure logic (covered by --self-check) ----------

def tick_to_sec(tick: float, tempos: list[tuple[int, float]]) -> float:
    """tempos = [(tick, bpm), ...] sorted, first at 0; 480 ticks per quarter note."""
    sec, (pt, bpm) = 0.0, tempos[0]
    for t, b in tempos[1:]:
        if t >= tick:
            break
        sec += (t - pt) * 60 / (bpm * 480)
        pt, bpm = t, b
    return sec + (tick - pt) * 60 / (bpm * 480)


def pitch_offset(midi: np.ndarray, tone: int) -> tuple[float, float]:
    """Median offset (semitones) of sung frames from the written tone, octave errors folded into -6..6, and the
    interquartile spread (small = steady)."""
    d = midi - tone
    d = d - 12 * np.round(d / 12)
    q1, med, q3 = np.percentile(d, [25, 50, 75])
    return float(med), float(q3 - q1)


def steady_off(med: float, spread: float) -> bool:
    return 1.0 <= abs(med) <= 2.5 and spread < 1.0


def early_release(active: np.ndarray, s: int, e: int, nxt: int) -> float | None:
    """Fraction of the note [s, e) the singer holds, if they stop before 80 % and stay silent until frame nxt
    (next note start minus the consonant guard, or e when nothing follows); else None. Sound after nxt is the
    next note's onset, also when nxt falls inside this note."""
    on = np.flatnonzero(active[s:min(e, nxt) if nxt > s else e])
    if not len(on) or e <= s:
        return None
    frac = (on[-1] + 1) / (e - s)
    stop = s + on[-1] + 1
    if frac >= 0.8 or active[stop:max(nxt, stop)].any():
        return None
    return float(frac)


def balance_db(v_rms: np.ndarray, b_rms: np.ndarray, mask: np.ndarray) -> float | None:
    """Vocal minus backing level (dB) over the frames in mask (where the vocal sings)."""
    if not mask.any():
        return None
    return float(10 * np.log10(np.mean(v_rms[mask] ** 2) / max(np.mean(b_rms[mask] ** 2), 1e-12)))


def parse_sections(text: str) -> list[tuple[str, int, int]]:
    """"verse:1-8,chorus:9-16" -> [("verse", 1, 8), ("chorus", 9, 16)] (bars, inclusive)."""
    out = []
    for item in filter(None, (x.strip() for x in text.split(","))):
        m = re.fullmatch(r"(.+):(\d+)-(\d+)", item)
        if not m:
            raise SystemExit(f"bad section '{item}', expected name:first-last")
        out.append((m.group(1), int(m.group(2)), int(m.group(3))))
    return out


def self_check():
    tm = [(0, 120.0), (1920, 60.0)]
    assert tick_to_sec(960, tm) == 1.0 and tick_to_sec(1920, tm) == 2.0 and tick_to_sec(2400, tm) == 3.0
    med, spread = pitch_offset(np.full(20, 62.0), 60)
    assert med == 2.0 and spread == 0 and steady_off(med, spread)
    med, _ = pitch_offset(np.full(20, 60 + 12 - 1.5), 60)  # an octave error plus a real dip
    assert abs(med + 1.5) < 1e-9 and steady_off(med, 0)
    assert not steady_off(*pitch_offset(np.full(20, 72.2), 60))  # octave error only
    assert not steady_off(*pitch_offset(np.r_[np.full(10, 58.0), np.full(10, 62.0)], 60))  # spread too wide
    act = np.zeros(200, bool)
    act[0:50] = True
    assert early_release(act, 0, 100, 150) == 0.5
    act[140:150] = True  # next consonant inside the guard: still a release
    assert early_release(act, 0, 100, 140) == 0.5
    legato = act.copy()
    legato[97:100] = True  # next note starts at 100, its onset smears in after nxt=96: still a release
    assert early_release(legato, 0, 100, 96) == 0.5
    act[120] = True  # sound in the gap: not a clean release
    assert early_release(act, 0, 100, 140) is None
    full = np.ones(100, bool)
    assert early_release(full, 0, 100, 100) is None
    full[85:] = False
    assert early_release(full, 0, 100, 100) is None  # 85 % is a normal end
    assert early_release(np.zeros(100, bool), 0, 100, 100) is None
    b = np.ones(10)
    assert abs(balance_db(2 * b, b, b > 0) - 6.0206) < 1e-3 and balance_db(b, b, b < 0) is None
    assert parse_sections("verse:1-8, chorus:9-16") == [("verse", 1, 8), ("chorus", 9, 16)]
    print("self-check ok")


# ---------- I/O ----------

def load_project(args) -> dict:
    """Lead notes [(tick, dur, tone, lyric)] (absolute ticks), tempos and ticks per bar from a .ustx or MIDI."""
    if args.ustx:
        import yaml
        with open(args.ustx, encoding="utf-8-sig") as f:
            p = yaml.safe_load(f)
        part = p["voice_parts"][args.part]
        ts = (p.get("time_signatures") or [{}])[0]
        notes = sorted((part.get("position", 0) + n["position"], n["duration"], n["tone"], str(n.get("lyric", "")))
                       for n in part["notes"])
        tempos = sorted((t["position"], float(t["bpm"])) for t in p["tempos"])
        bar = ts.get("beat_per_bar", 4) * 1920 // ts.get("beat_unit", 4)
    else:
        import mido
        m = mido.MidiFile(args.midi)
        k = 480 / m.ticks_per_beat
        tempos, bar, tracks = [], 1920, []
        for tr in m.tracks:
            tick, on, notes = 0, {}, []
            for msg in tr:
                tick += msg.time
                if msg.type == "set_tempo":
                    tempos.append((round(tick * k), mido.tempo2bpm(msg.tempo)))
                elif msg.type == "time_signature" and tick == 0:
                    bar = msg.numerator * 1920 // msg.denominator
                elif msg.type == "note_on" and msg.velocity > 0:
                    on[msg.note] = tick
                elif msg.type in ("note_off", "note_on") and msg.note in on:
                    t0 = on.pop(msg.note)
                    notes.append((round(t0 * k), round((tick - t0) * k), msg.note, ""))
            tracks.append(sorted(notes))
        idx = args.track if args.track is not None else next((i for i, t in enumerate(tracks) if t), 0)
        notes, tempos = tracks[idx], sorted(tempos)
    if not tempos or tempos[0][0] != 0:
        tempos.insert(0, (0, 120.0))
    if not notes:
        raise SystemExit("no notes in that part/track")
    return {"notes": notes, "tempos": tempos, "bar": bar}


def where(tick: int, bar: int) -> str:
    return f"bar {tick // bar + 1} beat {(tick % bar) / 480 + 1:g}"


def demucs(mix: str, outdir: str, py: str | None) -> tuple[str, str]:
    stem_dir = os.path.join(outdir, "htdemucs", os.path.splitext(os.path.basename(mix))[0])
    voc, rest = os.path.join(stem_dir, "vocals.wav"), os.path.join(stem_dir, "no_vocals.wav")
    if not (os.path.isfile(voc) and os.path.isfile(rest)):
        py = py or os.path.join(os.environ.get("LOCALAPPDATA", ""), "demucs", "venv", "Scripts", "python.exe")
        if not os.path.isfile(py):
            raise SystemExit("Demucs not found: pass --demucs-python (a python with demucs installed) "
                             "or give --ref-vocal / --ref-backing")
        print(f"separating {mix} with Demucs (a few minutes)...", flush=True)
        subprocess.run([py, "-m", "demucs", "--two-stems", "vocals", "-n", "htdemucs", "-o", outdir, mix], check=True)
    return voc, rest


def ref_stems(args) -> tuple[str, str | None]:
    if args.ref_vocal:
        return args.ref_vocal, args.ref_backing
    if not args.ref:
        raise SystemExit("give the original mix (REF) or --ref-vocal")
    return demucs(args.ref, os.path.join(os.path.dirname(os.path.abspath(args.ref)), "separated"), args.demucs_python)


def load(path: str) -> np.ndarray:
    import librosa
    return librosa.load(path, sr=SR, mono=True)[0]


def rms(y: np.ndarray) -> np.ndarray:
    import librosa
    return librosa.feature.rms(y=y, frame_length=2 * HOP, hop_length=HOP)[0]


def frame(sec: float) -> int:
    return max(0, int(round(sec * SR / HOP)))


# ---------- commands ----------

def cmd_notes(args):
    import librosa
    proj = load_project(args)
    voc, _ = ref_stems(args)
    y = load(voc)
    print("tracking pitch (pyin)...", flush=True)
    f0, voiced, _ = librosa.pyin(y, fmin=65, fmax=1100, sr=SR, frame_length=2048, hop_length=HOP)
    r = rms(y)[:len(f0)]
    db = 20 * np.log10(np.maximum(r, 1e-9))
    active = voiced & (db > np.percentile(db, 95) - 30)
    midi = librosa.hz_to_midi(np.where(voiced, f0, np.nan))
    notes, tempos, bar = proj["notes"], proj["tempos"], proj["bar"]
    sec = lambda t: args.offset + tick_to_sec(t, tempos)  # noqa: E731
    off, rel, longs, measured = [], [], 0, 0
    for i, (tick, dur, tone, lyric) in enumerate(notes):
        s, e = frame(sec(tick)), frame(sec(tick + dur))
        mid = midi[s + (e - s) // 5: e - (e - s) // 5]  # middle 60 %: skip scoops and releases
        mid = mid[~np.isnan(mid)]
        if len(mid) >= 5:
            measured += 1
            med, spread = pitch_offset(mid, tone)
            if steady_off(med, spread):
                off.append((i, tick, lyric, tone, med))
        if dur >= LONG:
            longs += 1
            nxt = frame(sec(notes[i + 1][0] - GUARD)) if i + 1 < len(notes) else e
            frac = early_release(active, s, e, nxt)
            if frac is not None:
                rel.append((i, tick, lyric, dur, frac))
    print(f"\n{measured}/{len(notes)} notes have a measurable reference pitch"
          + ("  <- low: check --offset and that REF is the same arrangement" if measured < 0.6 * len(notes) else ""))
    print(f"\n(a) {len(off)} notes sung a steady 1-2.5 semitones off the written note:")
    for i, tick, lyric, tone, med in off:
        print(f"  note {i:4d} {where(tick, bar):18s} '{lyric}' written {NAMES[tone % 12]}{tone // 12 - 1}, "
              f"sung {med:+.1f} st ({'below' if med < 0 else 'above'})")
    print(f"\n(b) {len(rel)} of {longs} long notes released early by the singer (sung part of the note):")
    for i, tick, lyric, dur, frac in rel:
        print(f"  note {i:4d} {where(tick, bar):18s} '{lyric}' {dur} ticks, sung {frac:.0%}")
    if rel:
        print(f"  median sung part {np.median([x[4] for x in rel]):.0%}; shorten those notes (or end them with a "
              "breath) instead of holding them to full length")


def cmd_balance(args):
    proj = load_project(args)
    rv, rb = ref_stems(args)
    if not rb:
        raise SystemExit("balance needs the reference backing too (--ref-backing, or REF for Demucs)")
    tempos, bar = proj["tempos"], proj["bar"]
    last_bar = (proj["notes"][-1][0] + proj["notes"][-1][1]) // bar + 1
    sections = parse_sections(args.sections) if args.sections else \
        [(f"bars {b}-{min(b + 7, last_bar)}", b, min(b + 7, last_bar)) for b in range(1, last_bar + 1, 8)]
    levels = {}
    for name, (v, b, offset) in {"ref": (rv, rb, args.offset), "render": (args.vocal, args.backing, args.render_offset)}.items():
        vr, br = rms(load(v)), rms(load(b))
        n = min(len(vr), len(br))
        vr, br = vr[:n], br[:n]
        vdb = 20 * np.log10(np.maximum(vr, 1e-9))
        sings = vdb > np.percentile(vdb, 95) - 30
        idx = np.arange(n)
        for sec_name, b0, b1 in sections:
            s = frame(offset + tick_to_sec((b0 - 1) * bar, tempos))
            e = frame(offset + tick_to_sec(b1 * bar, tempos))
            levels[(name, sec_name)] = balance_db(vr, br, sings & (idx >= s) & (idx < e))
    print("\n(c) vocal minus backing level (dB, where the vocal sings)")
    print(f"  {'section':20s} {'original':>9s} {'render':>9s} {'render-orig':>12s}")
    deltas = []
    for sec_name, _, _ in sections:
        a, b = levels[("ref", sec_name)], levels[("render", sec_name)]
        d = None if a is None or b is None else b - a
        if d is not None:
            deltas.append(d)
        fmt = lambda x: "-" if x is None else f"{x:+.1f}"  # noqa: E731
        print(f"  {sec_name:20s} {fmt(a):>9s} {fmt(b):>9s} {fmt(d):>12s}")
    if deltas:
        print(f"  median {np.median(deltas):+.1f} dB: positive = the synth lead sits louder than the original singer; "
              "turn it down by about that much before more tuning")


def cmd_loudness(args):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", args.render, "-af", "ebur128=peak=true",
                          "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    summary = out[out.rfind("Summary:"):]
    i = re.search(r"I:\s*(-?[\d.]+|-inf) LUFS", summary)
    tp = re.search(r"True peak:\s*Peak:\s*(-?[\d.]+|-inf) dBFS", summary)
    if not i:
        raise SystemExit(f"ffmpeg could not measure {args.render}:\n{out[-800:]}")
    print(f"(d) integrated {i.group(1)} LUFS, true peak {tp.group(1) if tp else '?'} dBTP"
          + ("  <- above -1 dBTP: may clip after encoding" if tp and float(tp.group(1)) > -1 else ""))
    if args.normalize:
        import soundfile as sf
        sr = sf.info(args.render).samplerate
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", args.render, "-af",
                        "loudnorm=I=-14:TP=-1:LRA=11", "-ar", str(sr), args.normalize], check=True)
        print(f"wrote {args.normalize} (-14 LUFS, -1 dBTP) for listening; keep the original for mastering")


def main():
    if sys.argv[1:] == ["--self-check"]:
        return self_check()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("separate")
    sp.add_argument("mix")
    sp.add_argument("outdir")
    sp.add_argument("--demucs-python")
    for name in ("notes", "balance"):
        p = sub.add_parser(name)
        p.add_argument("ref", nargs="?", help="original full mix")
        p.add_argument("--ref-vocal")
        p.add_argument("--ref-backing")
        p.add_argument("--demucs-python")
        src = p.add_mutually_exclusive_group(required=True)
        src.add_argument("--ustx")
        src.add_argument("--midi")
        p.add_argument("--part", type=int, default=0, help="voice part index in the .ustx")
        p.add_argument("--track", type=int, help="MIDI track (default: first with notes)")
        p.add_argument("--offset", type=float, default=0.0, help="seconds into the reference where tick 0 falls")
        if name == "balance":
            p.add_argument("--vocal", required=True, help="render: lead vocal stem")
            p.add_argument("--backing", required=True, help="render: backing stem")
            p.add_argument("--render-offset", type=float, default=0.0)
            p.add_argument("--sections", help="name:first-last bars, comma separated (default: 8-bar blocks)")
    lp = sub.add_parser("loudness")
    lp.add_argument("render")
    lp.add_argument("--normalize", metavar="OUT.wav")
    args = ap.parse_args()
    if args.cmd == "separate":
        for f in demucs(args.mix, args.outdir, args.demucs_python):
            print(f)
    else:
        {"notes": cmd_notes, "balance": cmd_balance, "loudness": cmd_loudness}[args.cmd](args)


if __name__ == "__main__":
    main()
