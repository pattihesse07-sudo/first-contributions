#!/usr/bin/env python3
"""Legt leise, selbst erzeugte Hintergrundmusik unter einen fertigen Clip und spricht die Hook am Anfang.

Die Musik wird hier per Code erzeugt (Akkorde, weicher Beat). Sie ist kein fremdes Werk und löst
keine Urheberrechts-Treffer aus. Die Hook spricht Piper (freie Sprachsynthese, deutsche Stimme Thorsten).

Beispiel:
  python3 gta6/werkzeuge/aufpeppen.py gta6/clips/papaplatte-01-fertig.mp4 "Papaplatte ballert ganz Südostasien voll"
Ergebnis: gta6/clips/papaplatte-01-final.mp4 (Bild unverändert kopiert)
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

SR = 48000
STIMME = Path.home() / ".local/share/piper/de_DE-thorsten-high.onnx"


def dauer(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(p)],
                         capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


def note(freq, n, env_a=0.02, env_r=0.4):
    t = np.arange(n) / SR
    ton = (np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * 2 * freq * t)
           + 0.15 * np.sin(2 * np.pi * 3 * freq * t))
    a = max(1, int(env_a * SR))
    env = np.ones(n)
    env[:a] = np.linspace(0, 1, a)
    env *= np.exp(-np.arange(n) / (env_r * SR))
    return ton * env


def musik(laenge, bpm=88, seed=7):
    """Lo-Fi-Loop: Am - F - C - G, weiche Flächen, Bass, Kick und Hi-Hat."""
    rng = np.random.default_rng(seed)
    n = int(laenge * SR)
    takt = 60 / bpm * 4
    out = np.zeros(n + int(takt * SR) * 3)
    akkorde = [(220.0, 261.63, 329.63), (174.61, 220.0, 261.63), (130.81, 164.81, 196.0), (196.0, 246.94, 293.66)]
    bass = [110.0, 87.31, 65.41, 98.0]
    schlag = 60 / bpm
    i = 0
    t0 = 0.0
    while t0 < laenge + takt:
        s = int(t0 * SR)
        ln = int(takt * SR)
        for f in akkorde[i % 4]:
            out[s:s + ln] += 0.10 * note(f, ln, env_a=0.3, env_r=2.5)
        for b in range(4):
            bs = s + int(b * schlag * SR)
            if b in (0, 2):
                out[bs:bs + int(0.5 * SR)] += 0.22 * note(bass[i % 4], int(0.5 * SR), env_r=0.25)
                kn = int(0.18 * SR)
                tk = np.arange(kn) / SR
                kick = np.sin(2 * np.pi * (55 + 90 * np.exp(-tk * 30)) * tk) * np.exp(-tk * 18)
                out[bs:bs + kn] += 0.35 * kick
            for h in (0, 0.5):
                hs = bs + int(h * schlag * SR)
                hn = int(0.04 * SR)
                out[hs:hs + hn] += 0.03 * rng.standard_normal(hn) * np.exp(-np.arange(hn) / (0.01 * SR))
        i += 1
        t0 += takt
    out = out[:n]
    # weicher machen: einfacher Tiefpass
    k = np.ones(8) / 8
    out = np.convolve(out, k, mode="same")
    fade = int(1.5 * SR)
    out[:fade] *= np.linspace(0, 1, fade)
    out[-fade:] *= np.linspace(1, 0, fade)
    return out / (np.max(np.abs(out)) + 1e-9) * 0.8


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clip")
    ap.add_argument("hook", help="Text, der am Anfang gesprochen wird")
    ap.add_argument("--musik-db", type=float, default=-24, help="Musikpegel relativ zum Stream-Ton (dB)")
    ap.add_argument("--tempo", type=float, default=1.0, help="Sprechtempo (kleiner = schneller)")
    ap.add_argument("--aus", default=None)
    a = ap.parse_args()

    clip = Path(a.clip)
    ziel = Path(a.aus) if a.aus else clip.with_name(clip.name.replace("-fertig", "-final"))
    if ziel.exists():
        sys.exit(f"{ziel} existiert schon, nichts überschrieben.")
    d = dauer(clip)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        sprache = tmp / "hook.wav"
        subprocess.run(["python3", "-m", "piper", "-m", str(STIMME), "--length-scale", str(a.tempo),
                        "-f", str(sprache)], input=a.hook.replace("\\n", " ").replace("\n", " ").encode(),
                       check=True, capture_output=True)
        hd = dauer(sprache)
        m = musik(d)
        import wave
        with wave.open(str(tmp / "musik.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((m * 32767).astype(np.int16).tobytes())
        ende = hd + 0.25
        # Stream-Ton während der gesprochenen Hook auf -14 dB absenken, Musik leise darunter
        fc = (f"[0:a]aresample={SR},volume='if(lt(t,{ende:.2f}),0.2,1)':eval=frame[stream];"
              f"[1:a]aresample={SR},volume=1.6,adelay=150|150[hook];"
              f"[2:a]aresample={SR},volume={10 ** (a.musik_db / 20):.4f}[bg];"
              f"[stream][hook][bg]amix=inputs=3:duration=first:normalize=0,"
              f"loudnorm=I=-14:TP=-1.5:LRA=11[a]")
        subprocess.run(["ffmpeg", "-n", "-v", "error", "-i", str(clip), "-i", str(sprache), "-i", str(tmp / "musik.wav"),
                        "-filter_complex", fc, "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "160k", "-ar", str(SR), "-movflags", "+faststart", str(ziel)],
                       check=True)
    print(json.dumps({"datei": str(ziel), "dauer_s": round(dauer(ziel), 2), "hook_s": round(hd, 2)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
