"""Mix mono WAV stems into one stereo WAV: resample, time-align, level-match, pan, peak-normalise.

usage (run isolated, stdlib only, Python 3.11+ with audioop):
  python -W ignore -I mix_stems.py OUT.wav "PATH|PAN|WEIGHT[|align]" "PATH|PAN|WEIGHT" ...

  PAN     -1 (left) .. +1 (right), equal-power law
  WEIGHT  gain after RMS-matching every stem to the same level (1.0 = equal; melody ~1.2)
  align   (optional flag) shift THIS stem to line up with the average envelope of the stems that are NOT flagged.
          Use it for a stem from another tool whose render starts late (one such synth lagged ~0.3 s). OpenUtau stems
          exported together already share one timeline and need no flag.

Example (an SATB-style spread; the bass comes from another tool):
  python -W ignore -I mix_stems.py out.wav ^
    "d\\line_bass.wav|-0.5|0.9|align" "d\\line_tenor.wav|-0.2|0.95" ^
    "d\\line_alto.wav|0.25|0.85" "d\\line_melody.wav|0.5|1.2"

Prints the offset it applied; check it is sensible. Output is 16-bit stereo, 44.1 kHz.
"""
import array
import audioop
import math
import struct
import sys
import wave

SR = 44100
WIN = SR // 100  # 10 ms envelope windows


def read(path):
    w = wave.open(path)
    assert w.getnchannels() == 1 and w.getsampwidth() == 2, f"{path}: need mono 16-bit"
    raw, sr = w.readframes(w.getnframes()), w.getframerate()
    if sr != SR:
        raw, _ = audioop.ratecv(raw, 2, 1, sr, SR, None)
    a = array.array("h")
    a.frombytes(raw)
    return [x / 32768 for x in a]


def env(x):
    return [math.sqrt(sum(v * v for v in x[i:i + WIN]) / WIN) for i in range(0, len(x) - WIN, WIN)]


def best_lag(ref, e, maxlag=80):
    """windows to shift e by to match ref; positive = e is late"""
    best = (-1e18, 0)
    for lag in range(-maxlag, maxlag + 1):
        s = sum(ref[i] * e[i + lag] for i in range(len(ref)) if 0 <= i + lag < len(e))
        if s > best[0]:
            best = (s, lag)
    return best[1]


def shift(x, n):  # n > 0 drops n samples from the start (earlier); n < 0 pads
    return x[n:] if n >= 0 else [0.0] * (-n) + x


def rms(x):
    return math.sqrt(sum(v * v for v in x) / max(1, len(x)))


def main():
    out, specs = sys.argv[1], sys.argv[2:]
    stems = []
    for s in specs:
        p = s.split("|")
        stems.append({"path": p[0], "pan": float(p[1]), "w": float(p[2]), "align": len(p) > 3 and p[3] == "align",
                      "x": read(p[0])})
    fixed = [s for s in stems if not s["align"]] or stems
    envs = [env(s["x"]) for s in fixed]
    m = min(map(len, envs))
    ref = [sum(e[i] for e in envs) / len(envs) for i in range(m)]
    for s in stems:
        if s["align"]:
            lag = best_lag(ref, env(s["x"]))
            s["x"] = shift(s["x"], lag * WIN)
            print(f"{s['path']}: shifted {-lag * 10} ms ({'was late' if lag > 0 else 'was early'})")
    target = 0.09
    for s in stems:
        g = target / rms(s["x"]) * s["w"]
        s["x"] = [v * g for v in s["x"]]
    n = max(len(s["x"]) for s in stems)
    L, R = [0.0] * n, [0.0] * n
    for s in stems:
        a = (s["pan"] + 1) * math.pi / 4
        gl, gr = math.cos(a), math.sin(a)
        for i, v in enumerate(s["x"]):
            L[i] += v * gl
            R[i] += v * gr
    k = 0.9 / max(max(map(abs, L)), max(map(abs, R)))
    w = wave.open(out, "wb")
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    buf = bytearray()
    for l, r in zip(L, R):
        buf += struct.pack("<hh", int(l * k * 32767), int(r * k * 32767))
    w.writeframes(bytes(buf)); w.close()
    print(f"wrote {out}  {n / SR:.2f}s  x{k:.2f}")


if __name__ == "__main__":
    main()

