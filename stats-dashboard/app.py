#!/usr/bin/env python3
"""Statistik-Dashboard für den Proud-Mountain-Server (https://stats.proud-mountain.com).

Jede Minute: wer online ist und TPS (RCON), Heap nach der letzten Garbage Collection (GC-Log des
Servers), RAM und CPU des Hosts (/proc), platzierte/abgebaute Blöcke aus der CoreProtect-Datenbank (nur
Leserechte). Stündlich ein Snapshot der Weltstatistiken (Tode, Mobs, Strecke …) für Heute/7 Tage. Sessions kommen aus den Server-Logs ("joined/left the game"),
damit auch die Zeit vor dem Dashboard zählt. Ereignisse und Messwerte landen in einer SQLite-Datei,
die Webseite (index.html) holt sich alles als JSON von /api/stats.

Standardbibliothek plus PyMySQL (für CoreProtect). Konfiguration per Umgebung, siehe ENV unten.
"""
import gzip, json, os, re, socket, sqlite3, struct, threading, time, zipfile
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

try:
    import pymysql  # nur für CoreProtect
except ImportError:
    pymysql = None

ENV = os.environ.get
DATA = ENV("MC_DATA", "/data")
DB_PATH = ENV("STATS_DB", "/stats/stats.db")
RCON = (ENV("RCON_HOST", "mc"), int(ENV("RCON_PORT", "25575")), ENV("RCON_PASSWORD", ""))
TZ = ZoneInfo(ENV("TZ", "Europe/Berlin"))
MAX_HEAP = ENV("MAX_MEMORY", "16G")
RESTART_AT = ENV("RESTART_AT", "06:00")  # täglicher Neustart (Cron auf dem Host)
ADDRESS = ENV("SERVER_ADDRESS", "server.proud-mountain.com")
CP_DB = (ENV("CP_DB_HOST", "db"), ENV("CP_DB_USER", "stats"), ENV("CP_DB_PASSWORD", ""), int(ENV("CP_DB_PORT", "3306")))  # nur Leserechte
INTERVAL = 60
KEEP_DAYS = 30
HERE = os.path.dirname(os.path.abspath(__file__))

LOG_LINE = re.compile(r"^\[(\d{2}\w{3}\d{4} \d{2}:\d{2}:\d{2})\.\d+\] \[([^\]]+)\] \[([^\]]*)\]: (.*)$")
ARCHIVE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(\d+)\.log\.gz$")
PLAYER_EVENT = re.compile(r"^(\w{3,16}) (joined|left) the game$")
TPS = re.compile(r"Overall: ([\d.]+) TPS \(([\d.]+) ms/tick\)")
GC = re.compile(r"(\d+)([KMG])->(\d+)([KMG])\((\d+)([KMG])\)")
COLOR = re.compile(r"\x1b\[[0-9;]*m|§.")
LANG_FILE = re.compile(r"^assets/[^/]+/lang/(de_de|en_us)\.json$")


def mb(n, unit):
    return int(n) * {"K": 1 / 1024, "M": 1, "G": 1024}[unit]


# --- RCON -------------------------------------------------------------------------------------------

def rcon(*commands):
    host, port, password = RCON
    with socket.create_connection((host, port), timeout=5) as s:
        def send(rid, typ, body):
            data = struct.pack("<ii", rid, typ) + body.encode() + b"\x00\x00"
            s.sendall(struct.pack("<i", len(data)) + data)

        def recv():
            def exact(n):
                buf = b""
                while len(buf) < n:
                    chunk = s.recv(n - len(buf))
                    if not chunk:
                        raise ConnectionError("RCON-Verbindung geschlossen")
                    buf += chunk
                return buf
            n = struct.unpack("<i", exact(4))[0]
            body = exact(n)
            return struct.unpack("<i", body[:4])[0], body[8:-2].decode(errors="replace")

        send(1, 3, password)
        if recv()[0] == -1:
            raise PermissionError("RCON-Passwort falsch")
        out = []
        for i, cmd in enumerate(commands, start=10):
            send(i, 2, cmd)
            out.append(COLOR.sub("", recv()[1]).strip())
        return out


# --- Datenbank --------------------------------------------------------------------------------------

def db():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS events (ts REAL, kind TEXT, name TEXT, UNIQUE (ts, kind, name));
        CREATE TABLE IF NOT EXISTS log_files (name TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS snapshots (ts INTEGER, name TEXT, data TEXT, PRIMARY KEY (ts, name));
        CREATE TABLE IF NOT EXISTS cp_state (prefix TEXT PRIMARY KEY, last_rowid INTEGER);
        CREATE TABLE IF NOT EXISTS cp_hourly (prefix TEXT, hour INTEGER, name TEXT, placed INTEGER, broken INTEGER,
                                              PRIMARY KEY (prefix, hour, name));
        CREATE TABLE IF NOT EXISTS metrics (ts REAL PRIMARY KEY, online INTEGER, players INTEGER, tps REAL,
                                            mspt REAL, heap_used REAL, heap_committed REAL, mem_used REAL,
                                            mem_total REAL, cpu REAL);
    """)
    return con


# --- Server-Logs ------------------------------------------------------------------------------------

def parse_lines(lines):
    """Ereignisse (ts, kind, name) und letzter Zeitstempel. kind: start, ready, stop, join, leave, eof."""
    events, last = [], None
    for line in lines:
        m = LOG_LINE.match(line.rstrip("\n"))
        if not m:
            continue
        stamp, thread, source, msg = m.groups()
        try:
            ts = datetime.strptime(stamp, "%d%b%Y %H:%M:%S").replace(tzinfo=TZ).timestamp()
        except ValueError:
            continue
        last = ts
        if thread != "Server thread/INFO":
            continue
        if source == "net.minecraft.server.MinecraftServer/":
            if msg == "Stopping server":
                events.append((ts, "stop", ""))
            elif e := PLAYER_EVENT.match(msg):
                events.append((ts, "join" if e.group(2) == "joined" else "leave", e.group(1)))
        elif source == "net.minecraft.server.dedicated.DedicatedServer/":
            if msg.startswith("Starting minecraft server version"):
                events.append((ts, "start", ""))
            elif msg.startswith("Done ("):
                events.append((ts, "ready", ""))
    return events, last


class LatestLog:
    """Liest logs/latest.log inkrementell (nur neue Zeilen), beginnt nach einer Rotation von vorn."""

    def __init__(self):
        self.inode, self.offset, self.rest, self.last = None, 0, "", None

    def read(self):
        path = os.path.join(DATA, "logs", "latest.log")
        try:
            st = os.stat(path)
        except FileNotFoundError:
            return []
        if st.st_ino != self.inode or st.st_size < self.offset:
            self.inode, self.offset, self.rest, self.last = st.st_ino, 0, "", None
        with open(path, "rb") as f:
            f.seek(self.offset)
            chunk = f.read()
        self.offset += len(chunk)
        text = self.rest + chunk.decode(errors="replace")
        lines = text.split("\n")
        self.rest = lines.pop()
        events, last = parse_lines(lines)
        self.last = last or self.last
        return events


def import_archives(con):
    """Rotierte Logs (YYYY-MM-DD-N.log.gz) einmalig einlesen. Ein eof-Ereignis merkt sich das Dateiende,
    damit Sessions bei einem Absturz dort enden statt beim nächsten Start."""
    known = {r[0] for r in con.execute("SELECT name FROM log_files")}
    folder = os.path.join(DATA, "logs")
    for name in sorted(os.listdir(folder)):
        if not ARCHIVE.match(name) or name in known:
            continue
        with gzip.open(os.path.join(folder, name), "rt", errors="replace") as f:
            events, last = parse_lines(f)
        if last:
            events.append((last, "eof", ""))
        con.executemany("INSERT OR IGNORE INTO events VALUES (?, ?, ?)", events)
        con.execute("INSERT INTO log_files VALUES (?)", (name,))
    con.commit()


def sessions(con, online, latest_last):
    """Sessions [name, start, end] aus allen Ereignissen; end None = gerade online."""
    done, open_, last, ready = [], {}, None, None
    order = {"start": 0, "eof": 1, "ready": 2, "join": 3, "leave": 4, "stop": 5}
    rows = sorted(con.execute("SELECT ts, kind, name FROM events"), key=lambda r: (r[0], order[r[1]]))
    for ts, kind, name in rows:
        if kind in ("start", "stop"):
            end = ts if kind == "stop" else (last or ts)
            done += [[n, s, max(s, end)] for n, s in open_.items()]
            open_ = {}
            ready = None
        elif kind == "ready":
            ready = ts
        elif kind == "join":
            if name in open_:
                done.append([name, open_[name], ts])
            open_[name] = ts
        elif kind == "leave" and name in open_:
            done.append([name, open_.pop(name), ts])
        last = ts
    now = time.time()
    for n, s in open_.items():
        if n in online:
            done.append([n, s, None])
        else:  # Server abgestürzt oder RCON gerade weg
            done.append([n, s, max(s, latest_last or last or s)])
    for n in online - set(open_):
        done.append([n, now, None])
    return done, ready


# --- Messwerte --------------------------------------------------------------------------------------

def heap():
    """Belegter Heap nach der letzten GC und reservierter Heap (MB), aus dem GC-Log des Servers."""
    path = os.path.join(DATA, "logs", "gc.log")
    try:
        if time.time() - os.path.getmtime(path) > 600:
            return None, None
        with open(path, "rb") as f:
            f.seek(max(0, os.path.getsize(path) - 16384))
            tail = f.read().decode(errors="replace")
    except OSError:
        return None, None
    found = GC.findall(tail)
    if not found:
        return None, None
    _, _, after, au, committed, cu = found[-1]
    return mb(after, au), mb(committed, cu)


def meminfo():
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":", 1)
            info[k] = int(v.split()[0]) / 1024
    return info["MemTotal"] - info["MemAvailable"], info["MemTotal"]


class Cpu:
    def __init__(self):
        self.prev = None

    def read(self):
        with open("/proc/stat") as f:
            v = [int(x) for x in f.readline().split()[1:]]
        idle, total = v[3] + v[4], sum(v[:8])
        prev, self.prev = self.prev, (idle, total)
        if not prev or total == prev[1]:
            return None
        return 100 * (1 - (idle - prev[0]) / (total - prev[1]))


# --- Namen von Blöcken, Items und Mobs ---------------------------------------------------------------

class Names:
    """Deutsche Namen aus den Sprachdateien: Vanilla (beim Docker-Build von Mojang geladen) und die der
    Mods (aus den Jars in data/mods, de_de vor en_us). Neu gelesen, wenn sich der Mods-Ordner ändert."""

    def __init__(self):
        self.stamp, self.de, self.en = False, {}, {}  # False: noch nie geladen (None: kein Mods-Ordner)

    def load(self):
        folder = os.path.join(DATA, "mods")
        try:
            stamp = os.path.getmtime(folder)
        except OSError:
            stamp = None
        if stamp == self.stamp:
            return
        de, en = {}, {}
        try:
            de.update(json.load(open(os.path.join(HERE, "lang_de_vanilla.json"))))
        except (OSError, ValueError):
            pass
        for jar in sorted(os.listdir(folder)) if stamp else ():
            if not jar.endswith(".jar"):
                continue
            try:
                with zipfile.ZipFile(os.path.join(folder, jar)) as z:
                    for entry in z.namelist():
                        m = LANG_FILE.match(entry)
                        if m:
                            target = de if m.group(1) == "de_de" else en
                            try:
                                target.update(json.loads(z.read(entry).decode("utf-8-sig")))
                            except ValueError:
                                pass
            except (OSError, zipfile.BadZipFile):
                pass
        self.stamp, self.de, self.en = stamp, de, en

    def get(self, ident, *kinds):
        ns, _, path = ident.partition(":")
        for table in (self.de, self.en):
            for kind in kinds:
                if (v := table.get(f"{kind}.{ns}.{path}")) and "%" not in v:
                    return v
        return path.replace("_", " ").capitalize()


names = Names()


# --- Spielerstatistiken der Welt -------------------------------------------------------------------

def whitelist():
    try:
        return {p["name"]: p["uuid"] for p in json.load(open(os.path.join(DATA, "whitelist.json")))}
    except (OSError, ValueError):
        return {}


def level_name():
    try:
        for line in open(os.path.join(DATA, "server.properties")):
            if line.startswith("level-name="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return "world"


def player_colors():
    """Feste Farbnummern (1-8) aus config/proudmountain/spielerfarben.json, dieselben wie im Chat."""
    try:
        farben = json.load(open(os.path.join(DATA, "config", "proudmountain", "spielerfarben.json")))["farben"]
        return {str(k): int(v) for k, v in farben.items() if 1 <= int(v) <= 8}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def assign_colors(order):
    """Spieler ohne Eintrag bekommen der Reihe nach die noch freien Farben."""
    fixed = player_colors()
    free = [c for c in range(1, 9) if c not in fixed.values()] or list(range(1, 9))
    out, i = {}, 0
    for name in order:
        if name in fixed:
            out[name] = fixed[name]
        else:
            out[name] = free[i % len(free)]
            i += 1
    return out


WALK = ("walk", "sprint", "crouch", "walk_on_water", "walk_under_water")
SNAPSHOT_KEYS = ("deaths", "mob_kills", "walk_km", "distance_km", "crafted")


def world_stats(uuid):
    try:
        s = json.load(open(os.path.join(DATA, level_name(), "stats", f"{uuid}.json")))["stats"]
    except (OSError, ValueError, KeyError):
        return None
    c = s.get("minecraft:custom", {})
    km = lambda keys: sum(c.get(f"minecraft:{k}_one_cm", 0) for k in keys) / 100000
    top = lambda cat, n: sorted(s.get(cat, {}).items(), key=lambda kv: -kv[1])[:n]
    return {
        "play_time": c.get("minecraft:play_time", 0) / 20,
        "deaths": c.get("minecraft:deaths", 0),
        "mob_kills": c.get("minecraft:mob_kills", 0),
        "walk_km": km(WALK),
        "swim_km": km(("swim",)),
        "distance_km": sum(v for k, v in c.items() if k.endswith("_one_cm") and k != "minecraft:fall_one_cm") / 100000,
        "fall_km": km(("fall",)),
        "jumps": c.get("minecraft:jump", 0),
        "mined": sum(s.get("minecraft:mined", {}).values()),
        "crafted": sum(s.get("minecraft:crafted", {}).values()),
        "facts": {
            "mined": [[names.get(k, "block", "item"), v] for k, v in top("minecraft:mined", 3)],
            "killed": [[names.get(k, "entity"), v] for k, v in top("minecraft:killed", 3)],
            "killed_by": [[names.get(k, "entity"), v] for k, v in top("minecraft:killed_by", 1)],
            "crafted": [[names.get(k, "item", "block"), v] for k, v in top("minecraft:crafted", 1)],
        },
    }


def snapshot_world(con, now, stats):
    """Einmal pro Stunde die Zählerstände speichern, daraus werden Werte für heute und 7 Tage."""
    hour = int(now // 3600) * 3600
    for name, w in stats.items():
        if w:
            con.execute("INSERT OR IGNORE INTO snapshots VALUES (?, ?, ?)",
                        (hour, name, json.dumps({k: w[k] for k in SNAPSHOT_KEYS})))


def world_delta(con, start, stats):
    """Zuwachs seit start je Spieler aus den Snapshots. Gibt es keinen Snapshot vor start, zählt der
    älteste (Zeitpunkt wird mit zurückgegeben, damit die Seite sagen kann, ab wann gezählt wird)."""
    base_ts = con.execute("SELECT MAX(ts) FROM snapshots WHERE ts <= ?", (start,)).fetchone()[0]
    if base_ts is None:
        base_ts = con.execute("SELECT MIN(ts) FROM snapshots").fetchone()[0]
    base = {n: json.loads(d) for n, d in con.execute("SELECT name, data FROM snapshots WHERE ts = ?", (base_ts,))}
    out = {}
    for name, w in stats.items():
        if w:
            b = base.get(name, {})
            out[name] = {k: max(0, w[k] - b.get(k, 0)) for k in SNAPSHOT_KEYS}
    return out, max(start, base_ts or start)


# --- CoreProtect (platzierte und abgebaute Blöcke) --------------------------------------------------

def cp_prefix():
    try:
        for line in open(os.path.join(DATA, "coreprotect", "config.yml")):
            if line.strip().startswith("table-prefix:"):
                p = line.split(":", 1)[1].strip().strip("'\"")
                return p if re.fullmatch(r"\w+", p) else None
    except OSError:
        pass
    return None


def coreprotect(con):
    """Neue Einträge aus <prefix>block stündlich je Spieler aufsummieren (nur rowid > zuletzt gesehen)."""
    prefix = cp_prefix()
    if not prefix or not CP_DB[2] or pymysql is None:
        return prefix  # ohne Datenbankzugang bleiben die bisher gezählten Werte stehen
    c = pymysql.connect(host=CP_DB[0], user=CP_DB[1], password=CP_DB[2], port=CP_DB[3], database="coreprotect",
                        connect_timeout=5, read_timeout=120)
    try:
        with c.cursor() as cur:
            row = con.execute("SELECT last_rowid FROM cp_state WHERE prefix = ?", (prefix,)).fetchone()
            last = row[0] if row else 0
            cur.execute(f"SELECT MAX(rowid) FROM {prefix}block")
            top = cur.fetchone()[0] or 0
            if top > last:
                cur.execute(f"SELECT rowid, user FROM {prefix}user")
                users = dict(cur.fetchall())
                cur.execute(f"SELECT user, action, time DIV 3600, COUNT(*) FROM {prefix}block "
                            "WHERE rowid > %s AND rowid <= %s AND action IN (0, 1) GROUP BY user, action, time DIV 3600",
                            (last, top))
                for uid, action, hour, n in cur.fetchall():
                    name = users.get(uid)
                    if not name or name.startswith("#"):  # #tnt, #fire usw.
                        continue
                    col = "placed" if action == 1 else "broken"
                    con.execute("INSERT OR IGNORE INTO cp_hourly VALUES (?, ?, ?, 0, 0)", (prefix, int(hour) * 3600, name))
                    con.execute(f"UPDATE cp_hourly SET {col} = {col} + ? WHERE prefix = ? AND hour = ? AND name = ?",
                                (n, prefix, int(hour) * 3600, name))
                con.execute("INSERT OR REPLACE INTO cp_state VALUES (?, ?)", (prefix, top))
                con.commit()
    finally:
        c.close()
    return prefix


def cp_sum(con, prefix, start=0):
    out = {}
    for name, placed, broken in con.execute("SELECT name, SUM(placed), SUM(broken) FROM cp_hourly "
                                            "WHERE prefix = ? AND hour >= ? GROUP BY name", (prefix, start)):
        out[name] = {"placed": placed, "broken": broken}
    return out


# --- Zusammenbauen ----------------------------------------------------------------------------------

def day_start(ts):
    d = datetime.fromtimestamp(ts, TZ)
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def day_labels(days, now):
    first = day_start(now) - timedelta(days=days - 1)
    return [(first + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]


def per_day(sess, labels, now):
    """Spielzeit in Stunden pro Spieler und Kalendertag (Sessions an Mitternacht geteilt)."""
    index = {d: i for i, d in enumerate(labels)}
    first = datetime.strptime(labels[0], "%Y-%m-%d").replace(tzinfo=TZ).timestamp()
    out = {}
    for name, start, end in sess:
        end = end or now
        t = max(start, first)
        while t < end:
            d = day_start(t)
            nxt = min(end, (d + timedelta(days=1)).timestamp())
            if (i := index.get(d.strftime("%Y-%m-%d"))) is not None:
                out.setdefault(name, [0.0] * len(labels))[i] += (nxt - t) / 3600
            t = nxt
    return out


def cp_per_day(con, prefix, labels):
    index = {d: i for i, d in enumerate(labels)}
    first = datetime.strptime(labels[0], "%Y-%m-%d").replace(tzinfo=TZ).timestamp()
    out = {"placed": {}, "broken": {}}
    for hour, name, placed, broken in con.execute("SELECT hour, name, placed, broken FROM cp_hourly "
                                                  "WHERE prefix = ? AND hour >= ?", (prefix, first)):
        if (i := index.get(day_start(hour).strftime("%Y-%m-%d"))) is not None:
            out["placed"].setdefault(name, [0] * len(labels))[i] += placed
            out["broken"].setdefault(name, [0] * len(labels))[i] += broken
    return out


def heatmap(sess, now, days=28):
    """Spielerstunden je Wochentag (Mo = 0) und Stunde der letzten 28 Tage und wie oft es diese Stunde
    im Zeitraum gab, daraus wird auf der Seite der Schnitt (Spieler online) gerechnet."""
    start = max(day_start(now - (days - 1) * 86400).timestamp(), min((s[1] for s in sess), default=now))
    sec = [[0.0] * 24 for _ in range(7)]
    for _, s, e in sess:
        t, e = max(s, start), e or now
        while t < e:
            d = datetime.fromtimestamp(t, TZ)
            nxt = min(e, (d.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).timestamp())
            sec[d.weekday()][d.hour] += nxt - t
            t = nxt
    count = [[0] * 24 for _ in range(7)]
    t = datetime.fromtimestamp(start, TZ).replace(minute=0, second=0, microsecond=0)
    while t.timestamp() < now:
        count[t.weekday()][t.hour] += 1
        t += timedelta(hours=1)
    return {"hours": [[round(v / 3600, 3) for v in row] for row in sec], "count": count, "since": start}


def series(con, now):
    """Letzte 24 h in 5-Minuten-Schritten."""
    rows = con.execute("SELECT ts, online, players, tps, mspt, heap_used, mem_used, cpu FROM metrics "
                       "WHERE ts >= ? ORDER BY ts", (now - 86400,)).fetchall()
    buckets = {}
    for r in rows:
        buckets.setdefault(int(r[0] // 300) * 300, []).append(r)
    out = []
    for b, rs in sorted(buckets.items()):
        def avg(i):
            v = [r[i] for r in rs if r[i] is not None]
            return round(sum(v) / len(v), 2) if v else None
        up = [r for r in rs if r[1]]
        out.append({"ts": b, "online": bool(up), "players": max((r[2] or 0) for r in rs),
                    "tps": min((r[3] for r in up if r[3] is not None), default=None), "mspt": avg(4),
                    "heap": avg(5), "mem": avg(6), "cpu": avg(7)})
    return out


def next_restart(now):
    h, m = map(int, RESTART_AT.split(":"))
    d = datetime.fromtimestamp(now, TZ).replace(hour=h, minute=m, second=0, microsecond=0)
    if d.timestamp() <= now:
        d += timedelta(days=1)
    return d.timestamp()


def playtime_since(mine, start, now):
    return sum(max(0, (e or now) - max(s, start)) for _, s, e in mine if (e or now) > start)


class Collector:
    def __init__(self):
        self.latest, self.cpu, self.snapshot = LatestLog(), Cpu(), b"{}"
        self.lock = threading.Lock()

    def poll(self):
        con = db()
        try:
            now = time.time()
            import_archives(con)
            con.executemany("INSERT OR IGNORE INTO events VALUES (?, ?, ?)", self.latest.read())
            online, players, max_players, tps, mspt = False, [], None, None, None
            try:
                listed, tps_out = rcon("list", "neoforge tps")
                m = re.match(r"There are (\d+) of a max of (\d+) players online:(.*)", listed, re.S)
                if m:
                    online, max_players = True, int(m.group(2))
                    players = [p.strip() for p in m.group(3).split(",") if p.strip()]
                if t := TPS.search(tps_out):
                    tps, mspt = float(t.group(1)), float(t.group(2))
            except (OSError, ConnectionError, PermissionError, struct.error) as e:
                print("RCON:", e, flush=True)
            heap_used, heap_committed = heap() if online else (None, None)
            mem_used, mem_total = meminfo()
            cpu = self.cpu.read()
            con.execute("INSERT OR REPLACE INTO metrics VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (now, online, len(players), tps, mspt, heap_used, heap_committed, mem_used, mem_total, cpu))
            con.execute("DELETE FROM metrics WHERE ts < ?", (now - KEEP_DAYS * 86400,))
            con.commit()
            try:
                prefix = coreprotect(con)
            except Exception as e:  # Datenbank weg: Rest der Seite trotzdem aktualisieren
                print("CoreProtect:", repr(e), flush=True)
                prefix = cp_prefix()

            names.load()
            sess, ready = sessions(con, set(players), self.latest.last)
            wl = whitelist()
            first_seen = {}
            for name, start, _ in sorted(sess, key=lambda s: s[1]):
                first_seen.setdefault(name, start)
            order = sorted(set(wl) | set(first_seen), key=lambda n: (first_seen.get(n, now), n.lower()))
            world = {n: world_stats(wl[n]) if n in wl else None for n in order}
            colors = assign_colors(order)
            snapshot_world(con, now, world)
            con.commit()

            starts = {"today": day_start(now).timestamp(), "week": now - 7 * 86400}
            deltas, since = {}, {}
            for key, start in starts.items():
                deltas[key], since[key] = world_delta(con, start, world)
            cp = {key: cp_sum(con, prefix, int(start // 3600) * 3600) if prefix else {} for key, start in starts.items()}
            cp["total"] = cp_sum(con, prefix) if prefix else {}

            table = []
            for name in order:
                mine = [s for s in sess if s[0] == name]
                current = next((s for s in mine if s[2] is None), None)
                ends = [s[2] for s in mine if s[2] is not None]
                w = world[name]
                periods = {}
                for key in ("today", "week", "total"):
                    snap = deltas[key].get(name, {}) if key != "total" else (w or {})
                    blocks = cp[key].get(name, {})
                    periods[key] = {
                        "playtime": playtime_since(mine, starts.get(key, 0), now),
                        "placed": blocks.get("placed", 0), "broken": blocks.get("broken", 0),
                        **{k: snap.get(k, 0) for k in SNAPSHOT_KEYS},
                    }
                table.append({
                    "name": name,
                    "color": colors[name],
                    "online": name in players,
                    "since": current[1] if current else None,
                    "last_seen": now if current else (max(ends) if ends else None),
                    "first_seen": first_seen.get(name),
                    "sessions": len(mine),
                    "longest": max(((e or now) - s for _, s, e in mine), default=0),
                    "periods": periods,
                    "world": w,
                })

            labels14 = day_labels(14, now)
            span = int((day_start(now) - day_start(min(first_seen.values(), default=now))).days) + 1
            labels_all = day_labels(min(max(span, 1), 120), now)
            cp_days = cp_per_day(con, prefix, labels14) if prefix else {"placed": {}, "broken": {}}
            cp_start = con.execute("SELECT MIN(hour) FROM cp_hourly WHERE prefix = ?", (prefix,)).fetchone()[0] if prefix else None
            snapshot = {
                "generated": now,
                "server": {
                    "address": ADDRESS, "online": online, "ready_since": ready if online else None,
                    "players": len(players), "max_players": max_players, "tps": tps, "mspt": mspt,
                    "heap_used": heap_used, "heap_committed": heap_committed, "heap_max": mb(MAX_HEAP[:-1], MAX_HEAP[-1]),
                    "mem_used": mem_used, "mem_total": mem_total, "cpu": cpu,
                    "next_restart": next_restart(now), "tracking_since": min(first_seen.values(), default=None),
                    "blocks_since": cp_start, "period_starts": starts, "world_since": since,
                },
                "players": table,
                "series": series(con, now),
                "daily": {"days": labels14, "playtime": per_day(sess, labels14, now),
                          "placed": cp_days["placed"], "broken": cp_days["broken"]},
                "cumulative": {"days": labels_all, "playtime": per_day(sess, labels_all, now)},
                "heatmap": heatmap(sess, now),
            }
            with self.lock:
                self.snapshot = json.dumps(snapshot, separators=(",", ":")).encode()
        finally:
            con.close()

    def run(self):
        while True:
            started = time.time()
            try:
                self.poll()
            except Exception as e:  # Dashboard soll weiterlaufen, auch wenn eine Runde scheitert
                print("Fehler beim Sammeln:", repr(e), flush=True)
            time.sleep(max(5, INTERVAL - (time.time() - started)))


collector = Collector()
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/favicon.svg": ("favicon.svg", "image/svg+xml")}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/stats":
            with collector.lock:
                body = collector.snapshot
            return self.reply(200, "application/json", body, "no-store")
        if path in STATIC:
            name, ctype = STATIC[path]
            with open(os.path.join(HERE, name), "rb") as f:
                return self.reply(200, ctype, f.read(), "max-age=300")
        self.reply(404, "text/plain; charset=utf-8", b"nicht gefunden")

    def reply(self, code, ctype, body, cache="no-cache"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    threading.Thread(target=collector.run, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", int(ENV("PORT", "8080"))), Handler).serve_forever()
