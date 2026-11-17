#!/usr/bin/env python3
"""Findet die stärksten Momente in einem Twitch-VOD, ohne etwas zu schneiden.

Lädt nur die Tonspur, sucht die lautesten Abschnitte (Lautstärke über dem Median des Streams),
transkribiert jeweils ein Fenster mit faster-whisper und schreibt eine Markdown-Liste mit
Zeitstempel, Grund und dem fertigen clip.py-Befehl. Die Tonspur wird danach gelöscht.

Beispiel:
  python3 gta6/werkzeuge/momente.py https://www.twitch.tv/videos/123 --name trymacs --anzahl 8
"""
import argparse
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np


def hms(s):
    s = int(s)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("link")
    ap.add_argument("--name", required=True, help="Kurzname des Streamers, z. B. trymacs")
    ap.add_argument("--anzahl", type=int, default=8)
    ap.add_argument("--fenster", type=int, default=50, help="Sekunden je Kandidat (Transkript)")
    ap.add_argument("--abstand", type=int, default=120, help="Mindestabstand der Kandidaten in Sekunden")
    ap.add_argument("--modell", default="small")
    ap.add_argument("--sprache", default="de")
    ap.add_argument("--abschnitt", default=None,
                    help="nur diesen Teil laden, z. B. 0-25000 (Sekunden); nötig bei laufenden Streams")
    a = ap.parse_args()

    env = dict(os.environ)
    p = env.get("HTTPS_PROXY") or env.get("https_proxy")
    if p:
        env.setdefault("http_proxy", p)
    env.setdefault("HF_HUB_DISABLE_XET", "1")
    os.environ.update({"HF_HUB_DISABLE_XET": env["HF_HUB_DISABLE_XET"]})

    arbeit = Path.cwd() / "gta6" / "quelle"
    arbeit.mkdir(parents=True, exist_ok=True)
    ton = arbeit / f"{a.name}-ton.m4a"
    titel = subprocess.run(["yt-dlp", "--print", "%(title)s|%(upload_date)s|%(duration)s", a.link],
                           capture_output=True, text=True, env=env).stdout.strip().split("|")
    if not ton.exists():
        extra = ["--download-sections", f"*{a.abschnitt}"] if a.abschnitt else []
        subprocess.run(["yt-dlp", "-q", "-f", "Audio_Only/ba", *extra, "-o", str(ton), a.link], check=True, env=env)
    roh = subprocess.run(["ffmpeg", "-v", "error", "-i", str(ton), "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(roh, dtype=np.int16).astype(np.float32) / 32768
    sr = 8000
    n = len(x) // sr
    db = 20 * np.log10(np.sqrt((x[:n * sr].reshape(n, sr) ** 2).mean(1)) + 1e-9)
    basis = float(np.median(db))
    w = 10
    sc = np.convolve(db, np.ones(w) / w, "valid")
    wahl = []
    for i in np.argsort(sc)[::-1]:
        if all(abs(int(i) - j) > a.abstand for j in wahl):
            wahl.append(int(i))
        if len(wahl) == a.anzahl:
            break
    wahl.sort()

    from faster_whisper import WhisperModel
    m = WhisperModel(a.modell, device="cpu", compute_type="int8")
    zeilen = []
    for k, i in enumerate(wahl, 1):
        start = max(0, i - a.fenster // 2)
        stueck = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(a.fenster), "-i", str(ton),
                                 "-ac", "1", "-ar", "16000", "-f", "wav", "-"], capture_output=True, check=True).stdout
        tmp = arbeit / f"{a.name}-{k}.wav"
        tmp.write_bytes(stueck)
        seg, _ = m.transcribe(str(tmp), language=a.sprache, vad_filter=True)
        text = " ".join(s.text.strip() for s in seg)
        tmp.unlink()
        offset = float(a.abschnitt.split("-")[0]) if a.abschnitt else 0.0
        start_vod = start + offset
        ende = start_vod + a.fenster
        zeilen.append(f"| {k} | {hms(start_vod)} | {hms(ende)} | +{sc[i] - basis:.1f} dB | {text[:400].replace('|', '/')} |"
                      f" `python3 gta6/werkzeuge/clip.py {a.link} {hms(start_vod)} {hms(start_vod + 45)} --nr {a.name}-{k:02d}` |")
        print(zeilen[-1], flush=True)

    ziel = Path.cwd() / "gta6" / f"momente-{a.name}.md"
    kopf = (f"# Momente: {a.name}\n\nVOD: {a.link}  \nTitel: {titel[0] if titel else ''}  \n"
            f"Gestreamt: {titel[1] if len(titel) > 1 else ''}, Länge {hms(float(titel[2])) if len(titel) > 2 and titel[2] else ''}  \n"
            f"Erstellt: {date.today().isoformat()} (Lautstärke-Spitzen, Transkript mit faster-whisper {a.modell})\n\n"
            "**Nicht schneiden ohne Erlaubnis des Streamers oder einer Kampagne.** Start und Ende vor dem Schnitt\n"
            "am Transkript feinjustieren (15 bis 60 Sekunden).\n\n"
            "| Nr | Start | Ende | Lauter als Median | Transkript (automatisch, ungeprüft) | Befehl |\n"
            "|---|---|---|---|---|---|\n")
    ziel.write_text(kopf + "\n".join(zeilen) + "\n", encoding="utf-8")
    ton.unlink()
    print(f"geschrieben: {ziel}")


if __name__ == "__main__":
    sys.exit(main())
