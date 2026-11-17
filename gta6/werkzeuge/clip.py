#!/usr/bin/env python3
"""Ein Befehl vom VOD-Link zum fertigen 9:16-Clip mit Wort-für-Wort-Untertiteln.

Nur für Material, das eine Kampagne oder der Rechteinhaber ausdrücklich erlaubt.
Postet und reicht nichts ein.

Beispiel:
  python3 gta6/werkzeuge/clip.py https://www.twitch.tv/videos/123 00:12:30 00:13:15 --nr 01
  python3 gta6/werkzeuge/clip.py LINK 1:02:10 1:02:50 --nr 02 --layout cam --cam 0,0,480,270

Ablauf: yt-dlp lädt nur den Abschnitt (gta6/quelle/), faster-whisper liefert Wortzeiten,
ffmpeg schneidet auf 1080x1920 (gta6/clips/<nr>-roh.mp4) und brennt die .ass-Untertitel ein
(gta6/clips/<nr>-fertig.mp4). Bestehende Dateien werden nie überschrieben.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd() / "gta6"
QUELLE, CLIPS = ROOT / "quelle", ROOT / "clips"


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def env_mit_proxy():
    """ffmpeg nutzt nur http_proxy; hinter dem Sitzungs-Proxy muss er gesetzt sein."""
    env = dict(os.environ)
    p = env.get("HTTPS_PROXY") or env.get("https_proxy")
    if p and not env.get("http_proxy"):
        env["http_proxy"] = p
    env.setdefault("HF_HUB_DISABLE_XET", "1")
    return env


def sek(t):
    teile = [float(x) for x in str(t).split(":")]
    s = 0.0
    for x in teile:
        s = s * 60 + x
    return s


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
         "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def laden(link, start, ende, nr, hoehe, env):
    QUELLE.mkdir(parents=True, exist_ok=True)
    ziel = QUELLE / f"{nr}.mp4"
    if ziel.exists():
        print(f"Quelle existiert schon: {ziel}")
        return ziel
    run(["yt-dlp", "--no-playlist", "--download-sections", f"*{start}-{ende}",
         "-f", f"bv*[height<={hoehe}]+ba/b[height<={hoehe}]/b",
         "--merge-output-format", "mp4", "-o", str(ziel), link], env=env)
    return ziel


def transkript(quelle, sprache, modell, env):
    os.environ.update({k: v for k, v in env.items() if k == "HF_HUB_DISABLE_XET"})
    from faster_whisper import WhisperModel
    m = WhisperModel(modell, device="cpu", compute_type="int8")
    seg, info = m.transcribe(str(quelle), language=sprache, word_timestamps=True,
                             vad_filter=True, beam_size=5)
    woerter = [{"w": w.word.strip(), "s": w.start, "e": w.end}
               for s in seg for w in (s.words or []) if w.word.strip()]
    return info.language, woerter


def ass_zeit(t):
    t = max(t, 0)
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def hook_zeilen(hook, dauer=3.0):
    """Hook oben im Spielbereich, schwarze Schrift auf weißem Kasten, die ersten Sekunden."""
    if not hook:
        return ""
    stil = ("Style: Hook,DejaVu Sans,74,&H00000000,&H00000000,&H00FFFFFF,&H00FFFFFF,1,0,0,0,"
            "100,100,0,0,3,16,0,8,80,80,1010,1\n")
    text = hook.replace("\n", "\\N")
    return stil, f"Dialogue: 1,{ass_zeit(0)},{ass_zeit(dauer)},Hook,,0,0,0,,{{\\fad(0,250)}}{text}"


def ass_schreiben(woerter, pfad, max_woerter=3, hook=None, credit=None):
    kopf = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,DejaVu Sans,96,&H00FFFFFF,&H0000FFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,7,2,2,60,60,480,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # Whisper liefert manchmal doppelte oder rückwärts laufende Zeiten: sortieren, Doppelte entfernen
    sauber = []
    for w in sorted(woerter, key=lambda x: x["s"]):
        if sauber and w["s"] < sauber[-1]["e"] - 0.05 and w["w"].lower() == sauber[-1]["w"].lower():
            continue
        if sauber and w["s"] < sauber[-1]["s"] + 0.02:
            w = dict(w, s=sauber[-1]["s"] + 0.02)
        sauber.append(w)
    woerter = sauber
    gruppen, akt = [], []
    for w in woerter:
        if akt and (len(akt) >= max_woerter or w["s"] - akt[-1]["e"] > 0.6
                    or akt[-1]["w"][-1:] in ".?!,"):
            gruppen.append(akt)
            akt = []
        akt.append(w)
    if akt:
        gruppen.append(akt)
    zeilen = []
    for k, g in enumerate(gruppen):
        naechste = gruppen[k + 1][0]["s"] if k + 1 < len(gruppen) else float("inf")
        for i, w in enumerate(g):
            ende = g[i + 1]["s"] if i + 1 < len(g) else min(w["e"] + 0.15, naechste)
            ende = max(ende, w["s"] + 0.05)
            text = " ".join(
                ("{\\c&H0000FFFF&}" + x["w"].upper() + "{\\c&H00FFFFFF&}") if j == i else x["w"].upper()
                for j, x in enumerate(g))
            zeilen.append((w["s"], ende, text))
    # Keine zwei Untertitel gleichzeitig: jedes Ende spätestens beim nächsten Start
    zeilen.sort(key=lambda z: z[0])
    zeilen = [f"Dialogue: 0,{ass_zeit(s)},{ass_zeit(min(e, zeilen[i + 1][0]) if i + 1 < len(zeilen) else e)},"
              f"Cap,,0,0,0,,{t}" for i, (s, e, t) in enumerate(zeilen)]
    if hook:
        stil, zeile = hook_zeilen(hook)
        kopf = kopf.replace("\n[Events]", stil + "\n[Events]")
        zeilen.append(zeile)
    if credit:
        stil = ("Style: Credit,DejaVu Sans,40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,"
                "100,100,0,0,1,3,1,2,40,40,70,1\n")
        kopf = kopf.replace("\n[Events]", stil + "\n[Events]")
        ende = max((w["e"] for w in woerter), default=0) + 5
        zeilen.append(f"Dialogue: 2,{ass_zeit(0)},{ass_zeit(max(ende, 600))},Credit,,0,0,0,,{credit}")
    pfad.write_text(kopf + "\n".join(zeilen) + "\n", encoding="utf-8")


def schneiden(quelle, roh, layout, cam, dauer):
    info = probe(quelle)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    w, h = v["width"], v["height"]
    if layout == "voll":
        vf = ("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1")
        args = ["-vf", vf]
    else:
        cx, cy, cw, ch = cam
        # Werte gelten für 1920x1080; auf echte Auflösung umrechnen
        f = w / 1920
        cx, cy, cw, ch = (int(round(x * f)) for x in (cx, cy, cw, ch))
        # Kamerastreifen so hoch wie das Seitenverhältnis des Ausschnitts (gerade Zahl, 480 bis 960)
        kh = min(960, max(480, int(round(1080 * ch / cw / 2)) * 2))
        sh = 1920 - kh
        # Spielbild ohne die Original-Kamera: Kamera rechts -> nur links davon, Kamera links -> rechts davon
        if cx + cw / 2 > w / 2:
            spiel = f"crop={cx}:{h}:0:0,"
        else:
            spiel = f"crop={w - cx - cw}:{h}:{cx + cw}:0,"
        fc = (f"[0:v]crop={cw}:{ch}:{cx}:{cy},scale=1080:{kh}:force_original_aspect_ratio=increase,"
              f"crop=1080:{kh},setsar=1[cam];[0:v]{spiel}scale=1080:{sh}:force_original_aspect_ratio=increase,"
              f"crop=1080:{sh},setsar=1[spiel];[cam][spiel]vstack[v]")
        args = ["-filter_complex", fc, "-map", "[v]", "-map", "0:a?"]
    run(["ffmpeg", "-n", "-v", "error", "-i", str(quelle), *args, "-t", str(dauer),
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(roh)])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("link")
    ap.add_argument("start", help="z. B. 00:12:30")
    ap.add_argument("ende", help="z. B. 00:13:15 (15 bis 60 Sekunden nach start)")
    ap.add_argument("--nr", required=True, help="Clipnummer, z. B. 01")
    ap.add_argument("--layout", choices=["voll", "cam"], default="voll")
    ap.add_argument("--cam", default="0,0,480,270", help="Kamera x,y,b,h im 1920x1080-Bild")
    ap.add_argument("--sprache", default=None, help="de oder en; leer = automatisch")
    ap.add_argument("--modell", default="small", help="Whisper-Modell (tiny, base, small)")
    ap.add_argument("--hoehe", type=int, default=1080)
    ap.add_argument("--mindestlaenge", type=float, default=61,
                    help="Kürzere Clips so oft wiederholen, bis sie länger sind (Sekunden, 0 = aus)")
    ap.add_argument("--credit", default=None, help="Quellenangabe, die durchgehend unten steht")
    ap.add_argument("--hook", default=None, help="Hook-Text für die ersten 3 Sekunden (\\n = Zeilenumbruch)")
    a = ap.parse_args()

    dauer = sek(a.ende) - sek(a.start)
    if not 15 <= dauer <= 60:
        sys.exit(f"Dauer {dauer:.1f}s liegt nicht bei 15 bis 60 Sekunden.")
    for tool in ("yt-dlp", "ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"{tool} fehlt im PATH.")
    env = env_mit_proxy()
    CLIPS.mkdir(parents=True, exist_ok=True)
    roh, fertig = CLIPS / f"{a.nr}-roh.mp4", CLIPS / f"{a.nr}-fertig.mp4"
    ass, wjson = CLIPS / f"{a.nr}.ass", CLIPS / f"{a.nr}-woerter.json"
    if fertig.exists():
        sys.exit(f"{fertig} existiert schon, nichts überschrieben.")

    quelle = laden(a.link, a.start, a.ende, a.nr, a.hoehe, env)
    if not roh.exists():
        schneiden(quelle, roh, a.layout, [int(x) for x in a.cam.split(",")], dauer)
    if wjson.exists():
        # Vorhandene (ggf. von Hand korrigierte) Wörter weiterverwenden
        d = json.loads(wjson.read_text(encoding="utf-8"))
        sprache, woerter = d["sprache"], d["woerter"]
        print(f"Nutze vorhandene Wörter aus {wjson}")
    else:
        sprache, woerter = transkript(roh, a.sprache, a.modell, env)
        wjson.write_text(json.dumps({"sprache": sprache, "woerter": woerter}, ensure_ascii=False,
                                    indent=1), encoding="utf-8")
    # Kurze Clips mehrfach hintereinander abspielen, bis sie über der Mindestlänge liegen
    basis = roh
    roh_dauer = float(probe(roh)["format"]["duration"])
    durchlaeufe = 1
    if a.mindestlaenge and roh_dauer < a.mindestlaenge:
        durchlaeufe = int(a.mindestlaenge // roh_dauer) + 1
        basis = CLIPS / f"{a.nr}-roh-x{durchlaeufe}.mp4"
        if not basis.exists():
            run(["ffmpeg", "-n", "-v", "error", "-stream_loop", str(durchlaeufe - 1), "-i", str(roh),
                 "-c", "copy", "-movflags", "+faststart", str(basis)])
        woerter = [dict(w, s=w["s"] + k * roh_dauer, e=w["e"] + k * roh_dauer)
                   for k in range(durchlaeufe) for w in woerter]
        print(f"Clip {roh_dauer:.1f}s -> {durchlaeufe}x abgespielt = {durchlaeufe * roh_dauer:.1f}s")
    ass.unlink(missing_ok=True)
    ass_schreiben(woerter, ass, hook=a.hook, credit=a.credit)
    run(["ffmpeg", "-n", "-v", "error", "-i", basis.name, "-vf", f"ass={ass.name}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", fertig.name], cwd=CLIPS)

    info = probe(fertig)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    ton = any(s["codec_type"] == "audio" for s in info["streams"])
    print(json.dumps({"datei": str(fertig), "breite": v["width"], "hoehe": v["height"],
                      "dauer_s": round(float(info["format"]["duration"]), 2), "ton": ton,
                      "sprache": sprache, "woerter": len(woerter),
                      "transkript": " ".join(w["w"] for w in woerter)}, ensure_ascii=False, indent=1))
    print("Prüfen: Standbilder ansehen, Wörter und Eigennamen gegen den Ton prüfen, dann /regel-check.")


if __name__ == "__main__":
    main()
