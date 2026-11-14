"""Vocal mix: lead + harmony stems over a backing segment.
Stems are pre-processed with ffmpeg (EQ, de-ess, compression); here: smooth stereo reverb, 1/8-note ping-pong delay,
harmony width, backing EQ dip + ducking, master limiting.
Usage: mix.py backing.wav lead.wav harmony.wav out.wav bpm [answer.wav]
Inputs at any sample rate (resampled to 44.1 kHz), mono or stereo.
"""
import sys
import numpy as np, soundfile as sf
from scipy.signal import fftconvolve, butter, sosfilt, resample_poly

backing_p, lead_p, harm_p, out_p, bpm = sys.argv[1:6]
bpm = float(bpm)
SR = 44100
rng = np.random.default_rng(7)


def load(p):
    x, sr = sf.read(p, always_2d=True)
    if sr != SR:  # OpenUtau/DiffSinger renders can be 48 kHz
        x = resample_poly(x, SR, sr, axis=0)
    return x if x.shape[1] == 2 else np.repeat(x, 2, axis=1)


def db(g):
    return 10 ** (g / 20)


def reverb_ir(rt60=1.5, predelay=0.025, lp=6000):
    n = int(rt60 * SR)
    t = np.arange(n) / SR
    env = np.exp(-6.9 * t / rt60)  # -60 dB at rt60
    ir = rng.standard_normal((n, 2)) * env[:, None]
    ir = sosfilt(butter(2, lp, "low", fs=SR, output="sos"), ir, axis=0)
    ir = sosfilt(butter(2, 250, "high", fs=SR, output="sos"), ir, axis=0)
    ir = np.vstack([np.zeros((int(predelay * SR), 2)), ir])
    return ir / np.sqrt((ir ** 2).sum(axis=0))


def reverb(x, ir):
    return np.stack([fftconvolve(x.mean(axis=1), ir[:, c])[: len(x)] for c in range(2)], axis=1)


def pingpong(x, delay_s, fb=0.32, repeats=5):
    out = np.zeros_like(x)
    d = int(delay_s * SR)
    mono = sosfilt(butter(2, [400, 5000], "band", fs=SR, output="sos"), x.mean(axis=1))
    for k in range(1, repeats + 1):
        if k * d >= len(x):
            break
        ch = (k - 1) % 2  # alternate L/R
        out[k * d:, ch] += (fb ** (k - 1)) * mono[: len(x) - k * d]
    return out


def envelope(x, attack=0.01, release=0.25):
    e = np.abs(x.mean(axis=1))
    a, r = np.exp(-1 / (attack * SR)), np.exp(-1 / (release * SR))
    out = np.empty_like(e)
    v = 0.0
    for i, s in enumerate(e[::32]):  # decimated for speed
        v = a * v + (1 - a) * s if s > v else r * v + (1 - r) * s
        out[i * 32:(i + 1) * 32] = v
    return out


bk, ld, hm = load(backing_p), load(lead_p), load(harm_p)
L = max(len(bk), len(ld), len(hm))
pad = lambda x: np.vstack([x, np.zeros((L - len(x), 2))])
bk, ld, hm = pad(bk), pad(ld), pad(hm)

# harmony: darker, wider (L/R with a 12 ms offset), well under the lead
hm = sosfilt(butter(2, 7000, "low", fs=SR, output="sos"), hm, axis=0)
hmono = hm.mean(axis=1)
off = int(0.012 * SR)
hm_w = np.stack([hmono, np.concatenate([np.zeros(off), hmono[:-off]])], axis=1) * db(-9)

vox_dry = ld + hm_w
ir = reverb_ir()
wet = reverb(ld, ir) * db(-13) + reverb(hm_w, ir) * db(-9) + pingpong(ld, 60 / bpm / 2) * db(-17)
if len(sys.argv) > 6:  # optional response stem: right of centre, a bit quieter, more echo
    rs = pad(load(sys.argv[6])).mean(axis=1) * db(-3)
    rs_p = np.stack([rs * 0.75, rs * 1.0], axis=1)
    vox_dry = vox_dry + rs_p
    wet = wet + reverb(rs_p, ir) * db(-10) + pingpong(rs_p, 60 / bpm / 2) * db(-13)
vox = vox_dry + wet

# backing: gentle 2.5 kHz dip, then duck up to ~3 dB under the lead
sos_lo = butter(2, [1800, 4000], "band", fs=SR, output="sos")
bk = bk - 0.25 * sosfilt(sos_lo, bk, axis=0)  # ~ -2.5 dB in the vocal presence band
env = envelope(ld)
duck = 1 - 0.3 * np.clip(env / (np.percentile(env[env > 0], 90) + 1e-9), 0, 1)
bk = bk * duck[:, None]

# level: dry lead RMS = backing RMS + VOX_DB where the lead sings (renders differ a lot in loudness per bank)
VOX_DB = 5.0
act = env > 0.2 * np.percentile(env[env > 0], 90)
rms = lambda x: np.sqrt((x[act] ** 2).mean()) + 1e-12
g = db(VOX_DB) * rms(bk) / rms(ld)
mix = bk + vox * g
print(f"vocals {VOX_DB:+.0f} dB over the backing (lead gain {20 * np.log10(g):+.1f} dB)")
peak = np.abs(mix).max()
mix = mix / peak * db(-1.0)  # ffmpeg alimiter + loudness afterwards
sf.write(out_p, mix, SR, subtype="PCM_24")
assert np.isfinite(mix).all()
print(f"wrote {out_p}: {L / SR:.2f}s, pre-norm peak {peak:.2f}")
