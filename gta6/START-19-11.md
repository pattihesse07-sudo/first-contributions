# Launch-Tag GTA 6 (19.11.2026): so läuft es

Stand 17.11.2026, getestet in der Umgebung `gta6-clipping`.

## Was bereit ist

| Teil | Stand |
|---|---|
| Umgebung `gta6-clipping` | Twitch, Twitch-VOD-Server, Kick, YouTube (Seiten), Content Rewards, Whop, Hugging Face freigegeben |
| Setup-Skript | installiert yt-dlp, faster-whisper (mit `av==13.1.0`), lädt das Whisper-Modell `small`, kopiert die Skills |
| Täglicher Check | 10:43 Uhr, sucht GTA-6- und Streamer-Kampagnen auf Content Rewards, Push aufs Handy |
| Werkzeug `gta6/werkzeuge/clip.py` | VOD-Abschnitt laden, 9:16, Wort-für-Wort-Untertitel, in einem Befehl |
| Test | Twitch-VOD, 45 s, 720p: 1080x1920, Ton, 129 Wörter, keine überlappenden Untertitel, rund 2 Minuten |

## Ablauf

1. Der tägliche Check meldet eine passende Kampagne. **Du trittst selbst bei** und liest die Regeln.
2. Du schreibst mir: "Clips für Kampagne X" (Link). Ich nutze `/stream-finder` und `/momente-finder`.
3. Pro Moment ein Befehl:

   ```bash
   python3 gta6/werkzeuge/clip.py https://www.twitch.tv/videos/<id> 01:02:10 01:02:50 --nr 01
   # Gesicht oben, Spiel unten (Kamera-Ausschnitt im 1920x1080-Bild):
   python3 gta6/werkzeuge/clip.py <link> 01:02:10 01:02:50 --nr 02 --layout cam --cam 1440,0,480,270
   ```

   Ergebnis: `gta6/clips/<nr>-fertig.mp4`, dazu `<nr>.ass` und `<nr>-woerter.json`.

   Clips unter 61 Sekunden werden automatisch so oft hintereinander abgespielt, bis sie länger sind
   (Untertitel laufen mit, Hook nur beim ersten Durchlauf). Abschalten mit `--mindestlaenge 0`, zum
   Beispiel wenn eine Kampagne eine Höchstlänge vorgibt (`/regel-check` prüft das).

   Untertitel korrigieren und Hook einbauen: Wörter in `<nr>-woerter.json` von Hand berichtigen
   (unsichere Wörter lieber streichen), `<nr>-fertig.mp4` löschen und den Befehl mit
   `--hook 'Zeile 1\nZeile 2'` erneut starten. Vorhandene Wörter werden dann übernommen.
   Musik und gesprochene Hook: `python3 gta6/werkzeuge/aufpeppen.py gta6/clips/<nr>-fertig.mp4 "Hook-Text"`
   ergibt `<nr>-final.mp4`. Die Musik wird selbst erzeugt (kein Urheberrecht Dritter). Wörter, die die
   Stimme schlecht ausspricht, nur im gesprochenen Text umschreiben (z. B. "Pappa Platte", "Geo Gesser").

4. `/hook-schreiber`, `/caption-und-hashtags`, `/regel-check`.
5. **Du postest** auf TikTok bzw. YouTube Shorts und reichst den Link in der Kampagne ein
   (bei Content Rewards innerhalb von 30 Minuten, Werbekennzeichnung beachten).

## Bekannte Grenzen

- **YouTube-Downloads gehen nicht** (YouTube verlangt Anmeldung vom Cloud-Server). Für YouTube-VODs:
  Abschnitt bei dir laden und hochladen.
- **Kick-VODs** (Adin Ross) lassen sich hier nicht laden: Kick blockt automatisierte Zugriffe. Abschnitte bei dir laden.
- Fokus-Streamer und Ladestatus: `gta6/streamer.md`.
- Twitch-VOD-Server wechseln. Wird ein neuer Server gesperrt, gebe ich ihn frei (dauert Sekunden).
- Ganze Mehrstunden-VODs mit Whisper zu transkribieren dauert auf der CPU lange. Momente zuerst über
  Twitch-Untertitel, Chat-Spitzen oder Lautstärke eingrenzen, dann nur Abschnitte transkribieren.
- Nur Streams clippen, die eine Kampagne oder der Streamer ausdrücklich erlaubt.
