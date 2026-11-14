"""Lay stems on the song timeline. Each source file@offset_s is summed in at offset_s seconds
(e.g. offset = where song bar 0 falls in the backing). Any sample rate in, 44.1 kHz stereo out.
Usage: assemble.py out.wav length_s file@offset [file@offset ...]
"""
import sys
import numpy as np, soundfile as sf
from scipy.signal import resample_poly

SR = 44100
out, length = sys.argv[1], float(sys.argv[2])
acc = np.zeros((int(length * SR), 2))
for spec in sys.argv[3:]:
    path, off = spec.rsplit("@", 1)
    x, sr = sf.read(path, always_2d=True)
    if sr != SR:
        x = resample_poly(x, SR, sr, axis=0)
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    i = int(round(float(off) * SR))
    n = min(len(x), len(acc) - i)
    acc[i:i + n] += x[:n]
sf.write(out, acc, SR, subtype="PCM_24")
print(f"{out}: {len(sys.argv) - 3} sources, peak {np.abs(acc).max():.2f}")
