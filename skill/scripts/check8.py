"""8-bar check for the user's ear: backing + click (high = beat 1) + the measured key's scale and tonic arpeggio.
If it sits in time and in tune, the analysis is right and vocals can be written on that grid.

  check8.py BACKING.wav facts.json OUT.wav [START_BAR]

facts.json comes from analyze_backing.py --json (with the same --speed you will use); BACKING.wav is the original
file: when facts.json has speed != 1 the backing is time-stretched with ffmpeg atempo (pitch kept).
"""
import json
import os
import subprocess
import sys
import tempfile

import librosa
import numpy as np
import soundfile as sf

NAMES = "C C# D D# E F F# G G# A A# B".split()
MAJOR, MINOR = [0, 2, 4, 5, 7, 9, 11, 12], [0, 2, 3, 5, 7, 8, 10, 12]
SR = 44100


def scale_notes(key: str) -> list[int]:
    """32 MIDI notes (one per beat): scale up and down, then the tonic triad arpeggio, in the A4 octave region."""
    root_name, mode = key.split()
    root = 60 + NAMES.index(root_name)
    if root < 64:
        root += 12  # keep it around a soprano register (E4..E5 roots)
    steps = MAJOR if mode == "major" else MINOR
    up = [root + s - 12 for s in steps]
    third = 4 if mode == "major" else 3
    arp = [root - 12, root - 12 + third, root - 5, root]
    return up + up[::-1] + arp * 2 + arp + [root + third, root, root - 5, root - 12 + third]


def main():
    backing, facts_p, out = sys.argv[1:4]
    start_bar = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    f = json.load(open(facts_p, encoding="utf-8"))
    src = backing
    if abs(f.get("speed", 1.0) - 1.0) > 1e-6:
        src = os.path.join(tempfile.mkdtemp(), "stretched.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", backing, "-af", f"atempo={f['speed']}", src], check=True)
    bar = f["bar_s"]
    beat = bar / 4
    seg_start = f["first_downbeat_s"] + start_bar * bar
    y, _ = librosa.load(src, sr=SR, mono=False, offset=seg_start, duration=8 * bar)
    y = np.atleast_2d(y)
    L = y.shape[1]
    add = np.zeros(L)

    def blip(at, freq, amp, dur=0.035):
        i = int(at * SR)
        k = np.arange(max(0, min(int(dur * SR), L - i)))
        add[i:i + len(k)] += amp * np.sin(2 * np.pi * freq * k / SR) * np.exp(-k / (0.008 * SR))

    def tone(at, midi, dur, amp=0.18):
        i, m = int(at * SR), int(dur * SR)
        k = np.arange(max(0, min(m, L - i)))
        hz = 440 * 2 ** ((midi - 69) / 12)
        env = np.minimum(1, k / (0.02 * SR)) * np.minimum(1, (m - k) / (0.05 * SR))  # soft attack/release
        add[i:i + len(k)] += amp * env * (np.sin(2 * np.pi * hz * k / SR) + 0.3 * np.sin(4 * np.pi * hz * k / SR))

    notes = scale_notes(f["key"])
    for k in range(32):
        blip(k * beat, 1760 if k % 4 == 0 else 1100, 0.5 if k % 4 == 0 else 0.25)
        tone(k * beat, notes[k], beat * 0.9)
    mix = y * 0.6 + add[None, :] * 0.8
    mix /= max(1.0, np.abs(mix).max() / 0.95)
    sf.write(out, mix.T, SR)
    print(f"wrote {out}: {f['tempo']} BPM, {f['key']}, bars {start_bar}-{start_bar + 7} "
          f"({seg_start:.2f}-{seg_start + 8 * bar:.2f} s of the {'stretched ' if src != backing else ''}backing)")


if __name__ == "__main__":
    assert len(scale_notes("A minor")) == 32 and scale_notes("A minor")[0] == 57  # A3 start, tonic triad later
    assert scale_notes("C major")[2] == 64  # C D E...
    main()
