"""Measure a backing track before writing vocals for it: tempo (fitted constant grid), first downbeat, key and
confidence, tuning offset, chord per bar, the repeating chord loop, loudness per bar.

Needs librosa (see SKILL.md §5b for the one-time venv setup). Not tied to VOCALOID: the numbers
are what any vocal synth (VOCALOID, OpenUtau, ...) needs to sit in time and in key.

  analyze_backing.py TRACK.wav                     report for one track
  analyze_backing.py TRACK.wav --speed 1.25        same, for the track sped up 1.25x with pitch kept
                                                   (ffmpeg -af atempo=1.25): tempo and times are converted
  analyze_backing.py TRACK.wav --json facts.json   also save beats/grid/chords for check8.py
  analyze_backing.py --table A.wav B.wav ...       one markdown row per file (tempo, key, steadiness)
"""
import argparse
import json
import sys

import librosa
import numpy as np

NAMES = "C C# D D# E F F# G G# A A# B".split()
MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])  # Krumhansl profiles
MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def keys_ranked(chroma_mean):
    sc = []
    for k in range(12):
        sc.append((float(np.corrcoef(chroma_mean, np.roll(MAJ, k))[0, 1]), f"{NAMES[k]} major"))
        sc.append((float(np.corrcoef(chroma_mean, np.roll(MIN, k))[0, 1]), f"{NAMES[k]} minor"))
    return sorted(sc, reverse=True)


def triads():
    out = []
    for r in range(12):
        for q, iv in (("", (0, 4, 7)), ("m", (0, 3, 7))):
            v = np.zeros(12)
            v[[(r + i) % 12 for i in iv]] = 1
            v[r] = 1.3  # root weighted
            out.append((NAMES[r] + q, v / np.linalg.norm(v)))
    return out


TRIADS = triads()


def best_chord(vec):
    v = vec / (np.linalg.norm(vec) + 1e-9)
    sc = sorted(((float(v @ t), n) for n, t in TRIADS), reverse=True)
    return sc[0][1], sc[0][0]


def find_loop(chords, sizes=(4, 8, 16)):
    """Smallest bar count whose chord pattern repeats best (share of bars equal to the bar one loop later)."""
    best = None
    for p in sizes:
        if len(chords) < 2 * p:
            continue
        same = np.mean([chords[i] == chords[i + p] for i in range(len(chords) - p)])
        if best is None or same > best[1] + 0.05:
            best = (p, float(same))
    return best


def analyze(path, speed=1.0, beats_per_bar=4, detail=True):
    y, sr = librosa.load(path, sr=22050, mono=True)
    dur = len(y) / sr
    tuning = float(librosa.estimate_tuning(y=y, sr=sr))
    y_h, y_p = librosa.effects.hpss(y)
    onset = librosa.onset.onset_strength(y=y_p, sr=sr)
    _, beats = librosa.beat.beat_track(onset_envelope=onset, sr=sr, units="frames")
    bt = librosa.frames_to_time(beats, sr=sr)
    if len(bt) < 8:
        raise ValueError("too few beats found (no steady pulse?)")
    period, t0 = np.polyfit(np.arange(len(bt)), bt, 1)  # constant grid = what a fixed-tempo editor can follow
    worst_ms = float(np.abs(bt - (t0 + np.arange(len(bt)) * period)).max() * 1000)
    # downbeat: the beat phase with the most low-end (kick) onset energy
    S = np.abs(librosa.stft(y_p))
    low = librosa.onset.onset_strength(S=librosa.amplitude_to_db(S[:12]), sr=sr)  # bins below ~120 Hz
    phase_sc = [float(np.mean(low[beats[p::beats_per_bar]])) for p in range(beats_per_bar)]
    ph = int(np.argmax(phase_sc))
    first_down = float(t0 + ph * period)
    while first_down - beats_per_bar * period >= bt[0] - period / 2:
        first_down -= beats_per_bar * period
    chroma = librosa.feature.chroma_cqt(y=y_h, sr=sr, tuning=tuning)
    keys = keys_ranked(chroma.mean(axis=1))
    out = {
        "file": path.replace("\\", "/").split("/")[-1], "speed": speed,
        "tempo": round(60 / period * speed, 3), "first_downbeat_s": round(first_down / speed, 3),
        "grid_max_deviation_ms": round(worst_ms / speed, 1), "steady": worst_ms < 40,
        "downbeat_confidence": round(phase_sc[ph] / (sorted(phase_sc)[-2] + 1e-9), 2),
        "key": keys[0][1], "key_r": round(keys[0][0], 3), "runner_up": f"{keys[1][1]} ({keys[1][0]:.3f})",
        "tuning_cents": round(tuning * 100, 1), "duration_s": round(dur / speed, 1),
        "beats_tracked_until_s": round(float(bt[-1]) / speed, 1),
    }
    if not detail:
        return out
    hop = 512
    bass = librosa.feature.chroma_cqt(y=y_h, sr=sr, hop_length=hop, fmin=librosa.note_to_hz("C1"), n_octaves=2)
    times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr, hop_length=hop)
    rms = librosa.feature.rms(y=y)[0]
    rt = librosa.frames_to_time(np.arange(len(rms)), sr=sr)
    bar_len = beats_per_bar * period
    bars = []
    k = 0
    while first_down + (k + 1) * bar_len <= dur:
        a, b = first_down + k * bar_len, first_down + (k + 1) * bar_len
        m = (times >= a) & (times < b)
        name, score = best_chord(chroma[:, m].mean(axis=1) + 0.5 * bass[:, m].mean(axis=1))
        level = float(rms[(rt >= a) & (rt < b)].mean())
        bars.append({"bar": k, "start_s": round(a / speed, 3), "chord": name, "fit": round(score, 2), "rms": level})
        k += 1
    top = max(b["rms"] for b in bars) or 1.0
    for b in bars:
        b["db"] = round(20 * np.log10(max(b["rms"], 1e-9) / top), 1)
        del b["rms"]
    loop = find_loop([b["chord"] for b in bars])
    out.update({
        "bar_s": round(bar_len / speed, 4), "bars": bars,
        "loop": {"bars": loop[0], "repeat_share": round(loop[1], 2),
                 "chords": [b["chord"] for b in bars[:loop[0]]]} if loop else None,
        "beats_s": [round(float(t) / speed, 3) for t in bt],
    })
    return out


def report(r):
    print(f"{r['file']}  (speed x{r['speed']})")
    print(f"  tempo        {r['tempo']} BPM  (grid fits tracked beats within {r['grid_max_deviation_ms']} ms: "
          f"{'steady, a fixed-tempo editor can follow it' if r['steady'] else 'NOT steady'})")
    print(f"  first beat 1 {r['first_downbeat_s']} s  (downbeat {r['downbeat_confidence']}x stronger than next phase)")
    print(f"  key          {r['key']}  r={r['key_r']}  (runner-up {r['runner_up']})")
    print(f"  tuning       {r['tuning_cents']:+} cents from A440")
    print(f"  length       {r['duration_s']} s, beat tracked until {r['beats_tracked_until_s']} s")
    if r.get("loop"):
        lp = r["loop"]
        print(f"  chord loop   {lp['bars']} bars, repeats {int(lp['repeat_share'] * 100)}%: {' | '.join(lp['chords'])}")
    print(f"  bar length   {r['bar_s']} s")
    print("  bar  start_s  chord  fit   dB")
    for b in r.get("bars", []):
        print(f"  {b['bar']:3d}  {b['start_s']:7.2f}  {b['chord']:5s}  {b['fit']:.2f}  {b['db']:5.1f} "
              + "#" * max(0, int(30 + b['db'])))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--speed", type=float, default=1.0, help="tempo factor the track will be played at (pitch kept)")
    ap.add_argument("--beats-per-bar", type=int, default=4)
    ap.add_argument("--json", help="write the full analysis (one file) to this path")
    ap.add_argument("--table", action="store_true", help="markdown table for many files")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.table:
        print("| Track | Tempo | Key | r | Runner-up | Steady? |\n|---|---|---|---|---|---|")
        for f in a.files:
            try:
                r = analyze(f, a.speed, a.beats_per_bar, detail=False)
                print(f"| {r['file']} | {r['tempo']:.1f} | {r['key']} | {r['key_r']:.2f} | {r['runner_up']} | "
                      f"{'yes' if r['steady'] else 'no'} ({r['grid_max_deviation_ms']:.0f} ms) |", flush=True)
            except Exception as e:  # noqa: BLE001 - keep going through a batch
                print(f"| {f} | error: {e} | | | | |", flush=True)
        return
    for f in a.files:
        r = analyze(f, a.speed, a.beats_per_bar)
        report(r)
        if a.json:
            with open(a.json, "w", encoding="utf-8") as fh:
                json.dump(r, fh)


if __name__ == "__main__":
    # self-checks: key profile rotation, triad templates, loop finder
    assert keys_ranked(MAJ.copy())[0][1] == "C major"
    assert best_chord(np.array([0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0.0]) + np.eye(12)[0])[0] == "Am"
    assert find_loop(["F", "G"] * 8)[0] == 4
    assert find_loop(["F", "F", "G", "Am", "Am", "Am", "Dm", "Am"] * 3)[0] == 8
    main()
