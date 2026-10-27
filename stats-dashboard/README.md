# Statistik-Dashboard

Öffentliche Seite https://stats.proud-mountain.com: wer online ist und seit wann, wann jemand zuletzt da war, Spielzeit pro Tag, Server-Auslastung (TPS, RAM, CPU) und ein paar Werte aus den Weltstatistiken. Positionen werden bewusst nicht angezeigt.

- `app.py` (nur Python-Standardbibliothek) sammelt jede Minute: `list` und `neoforge tps` per RCON, belegten Heap aus `logs/gc.log` (JVM-Option im Compose-Setup), RAM/CPU des Hosts aus `/proc`. Sessions kommen aus den Server-Logs (`joined/left the game`, auch rotierte `*.log.gz`), deshalb zählt auch die Zeit vor dem Dashboard. Alles landet in SQLite (`/stats/stats.db`), die Seite holt sich `/api/stats`.
- `index.html` ist die ganze Oberfläche (kein Build, keine externen Skripte).
- Läuft auf dem Server als Service `stats` in `~/docker/minecraft/compose.yaml`, nach außen über den Service `tunnel` (Cloudflare Tunnel, Route `stats.proud-mountain.com -> http://stats:8080`).

Update:

```sh
rsync -a --delete --exclude __pycache__ stats-dashboard/ fedora-server:docker/minecraft/stats-dashboard/
ssh fedora-server 'cd ~/docker/minecraft && docker compose up -d --build stats'
```

Wird nicht per packwiz ausgeliefert (liegt außerhalb von `packwiz/`).
