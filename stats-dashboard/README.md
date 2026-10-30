# Statistik-Dashboard

Öffentliche Seite https://stats.proud-mountain.com: wer online ist und seit wann, wann jemand zuletzt da war, Server-Auslastung (TPS, RAM, CPU), wann gespielt wird (Heatmap), Spielzeit und platzierte Blöcke pro Tag, Wettrennen der Gesamtspielzeit, Rangliste und Tabelle für Heute / 7 Tage / Gesamt (Spielzeit, platziert, abgebaut, Mobs, zu Fuß, Tode, Strecke, Hergestelltes) mit Summe für alle zusammen, Trophäenwand der Bosse (wer welchen Boss wie oft besiegt hat und wer zuerst) und Steckbriefe pro Spieler (Lieblingsblock, -mob, Todesursache …). Positionen werden bewusst nicht angezeigt.

- `app.py` (nur Python-Standardbibliothek) sammelt jede Minute: `list` und `neoforge tps` per RCON, belegten Heap aus `logs/gc.log` (JVM-Option im Compose-Setup), RAM/CPU des Hosts aus `/proc`. Sessions kommen aus den Server-Logs (`joined/left the game`, auch rotierte `*.log.gz`), deshalb zählt auch die Zeit vor dem Dashboard. Platzierte/abgebaute Blöcke zählt es stündlich aus der CoreProtect-Datenbank (MariaDB-Benutzer `stats`, nur `SELECT`, liest nur neue Zeilen). Tode, Mobs, Strecke usw. kommen aus `world/stats/*.json`; davon wird stündlich ein Snapshot gespeichert, daraus werden die Werte für Heute und 7 Tage (erst ab dem ersten Snapshot, die Seite sagt ab wann). Die Bossliste steht in `BOSSES` in `app.py`; da die Statistik-Dateien keine Zeitstempel haben, merkt sich das Dashboard selbst, wann ein Sieg zum ersten Mal auftaucht (Siege von vor dem Start der Trophäenwand zählen als „vor dem …“). Alles landet in SQLite (`/stats/stats.db`), die Seite holt sich `/api/stats`.
- Namen von Blöcken, Items und Mobs: Vanilla auf Deutsch lädt `fetch_lang.py` beim Docker-Build von Mojang (nicht im Repo), die der Mods liest `app.py` aus den Jars in `data/mods` (de_de, sonst en_us).
- Spielerfarben kommen aus `config/proudmountain/spielerfarben.json` im Pack (dieselbe Datei färbt per KubeJS `spielerfarben.js` die Namen im Chat). Per `/invite` eingeladene Spieler bekommen ihre Farbe beim Einladen (`config/proudmountain/einladungen.json`, KubeJS `invites.js`). Wer in beiden fehlt, bekommt die nächste freie Farbe.
- `index.html` ist die ganze Oberfläche (kein Build, keine externen Skripte).
- Läuft auf dem Server als Service `stats` in `~/docker/minecraft/compose.yaml`, nach außen über den Service `tunnel` (Cloudflare Tunnel, Route `stats.proud-mountain.com -> http://stats:8080`).

Update:

```sh
rsync -a --delete --exclude __pycache__ --exclude lang_de_vanilla.json stats-dashboard/ fedora-server:docker/minecraft/stats-dashboard/
ssh fedora-server 'cd ~/docker/minecraft && docker compose up -d --build stats'
```

Wird nicht per packwiz ausgeliefert (liegt außerhalb von `packwiz/`).
