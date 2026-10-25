#!/usr/bin/env python3
"""packwiz-Pack (Auto-Updates über GitHub) und Prism-Instanz aus mods.resolved.json bauen.

usage: packwiz.py <mods.resolved.json> <packwiz-Ordner> <Ausgabe-Ordner>

- packwiz-Ordner: pack.toml + index.toml + */*.pw.toml (Download-Metadaten, keine Jars) + Configs, KubeJS usw.
  Configs und Skripte werden direkt dort gepflegt (Quelle). Neu geschrieben werden nur die .pw.toml-Dateien,
  index.toml und pack.toml; server-overrides/ wird hineinkopiert. Danach committen und pushen.
  Liegt exakt dieselbe Datei (SHA1) auf Modrinth, wird von dort geladen, sonst von CurseForge. Modrinth
  erlaubt immer Launcher-Downloads, so entfallen manuelle Downloads für dort gespiegelte Mods.
  Eigene Mods aus extra-mods/ (EXTRA_MODS) werden direkt aus dem GitHub-Repo geladen, Dateien, die es nur
  auf Modrinth gibt (MODRINTH_FILES), direkt von dort.
- Ausgabe-Ordner: <Slug>-Prism.zip, eine Prism-Launcher-Instanz, die vor jedem Start per
  packwiz-installer-bootstrap.jar den Stand von PACK_URL holt. Muss nur einmal importiert werden.
  Enthält eine servers.dat mit SERVER, damit der Server nach dem Import schon in der Serverliste steht.
"""
import hashlib, json, os, shutil, struct, sys, urllib.parse, urllib.request, zipfile
from cf import post

NAME, VERSION, AUTHOR = "Proud Mountain SMP", "2.0.0", "Tim"  # wie in package.py
SLUG = NAME.replace(" ", "")
MC, NEOFORGE = "1.21.1", "21.1.256"
PACK_URL = "https://raw.githubusercontent.com/Stolzenberg/minecraft-modpack-proud-mountain-smp/main/packwiz/pack.toml"
SERVER = (NAME, "server.proud-mountain.com")  # Eintrag in der Serverliste (Name, Adresse)
# Eigene Mods aus extra-mods/ (Quelle im gleichnamigen Unterordner): Datei -> (Name, Seite)
EXTRA_MODS = {"proud-mountain-tweaks-2.4.0.jar": ("Proud Mountain Tweaks", "both")}
EXTRA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "extra-mods")
RAW_BASE = PACK_URL.rsplit("/packwiz/", 1)[0]
# Nur auf Modrinth: Pfad im Pack -> (Name, Seite, Projekt-ID, Versions-ID, Dateiname, SHA1)
MODRINTH_FILES = {
    "resourcepacks/block-overlays.pw.toml": ("Block Overlays", "client", "ZYV3OmS5", "Ao5BMsy0",
                                             "Overlays V75 MC1.20-1.21.11.zip", "1bf7668d53b2fdb7bd42b5718c45a8e7e4e0ec56"),
    "resourcepacks/diagonal-perfect-rails-3d.pw.toml": ("Diagonal Perfect Rails 3D PBR", "client", "GpbiI09r", "OuhpP9gE",
                                                        "DiagonalPerfectRails2.1.zip", "1bdf7c6b30d5a591d5059350eca27a65955b002d"),
    "resourcepacks/rustic.pw.toml": ("Rustic", "client", "uL4WlbKR", "wdlaSp9Y",
                                     "Rustic 1.6 [1.21-1.21.1].zip", "684eb6ab8419ded0a7800b94f082043675bdd59a"),
    "resourcepacks/variated.pw.toml": ("Variated", "client", "FvMA7P5s", "FL39DY4Q",
                                       "Variated.zip", "e910eb6e98720f70d8c4647ad695251e1cbc144c"),
}
# Persönliche Einstellungen: nur bei der Erstinstallation schreiben, Updates überschreiben sie nicht
PRESERVE = ("config/iris.properties",)
FOLDER = {6: "mods", 6552: "shaderpacks", 12: "resourcepacks"}
BOOTSTRAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "packwiz-installer-bootstrap.jar")


def q(s):
    return json.dumps(s, ensure_ascii=False)  # JSON-Strings sind gültige TOML-Basic-Strings


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def servers_dat(name, ip):
    """Minecrafts servers.dat (unkomprimiertes NBT) mit einem einzigen Servereintrag."""
    def s(v):
        b = v.encode()
        return struct.pack(">H", len(b)) + b
    entry = b"\x08" + s("name") + s(name) + b"\x08" + s("ip") + s(ip) + b"\x01" + s("hidden") + b"\x00" + b"\x00"
    return b"\x0a" + s("") + b"\x09" + s("servers") + b"\x0a" + struct.pack(">i", 1) + entry + b"\x00"


def modrinth(hashes):
    """SHA1 -> (Download-URL, Projekt-ID, Versions-ID) für alle Dateien, die identisch auf Modrinth liegen."""
    req = urllib.request.Request("https://api.modrinth.com/v2/version_files", method="POST",
                                 data=json.dumps({"hashes": hashes, "algorithm": "sha1"}).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "proud-mountain-smp-packwiz"})
    with urllib.request.urlopen(req, timeout=120) as r:
        res = json.load(r)
    return {h: (next(f["url"] for f in v["files"] if f["hashes"]["sha1"] == h), v["project_id"], v["id"])
            for h, v in res.items()}


all_mods = sorted(json.load(open(sys.argv[1])), key=lambda m: m["name"].lower())
pack, out = sys.argv[2], sys.argv[3]
server_overrides = os.path.join(os.path.dirname(os.path.abspath(pack)), "server-overrides")

if not os.path.exists(os.path.join(pack, "pack.toml")):
    sys.exit(f"{pack} ist kein packwiz-Ordner, breche ab")
# Nur Generiertes entfernen, damit entfernte Mods keine verwaisten .pw.toml hinterlassen
for folder in set(FOLDER.values()):
    for name in os.listdir(os.path.join(pack, folder)) if os.path.isdir(os.path.join(pack, folder)) else ():
        if name.endswith(".pw.toml"):
            os.remove(os.path.join(pack, folder, name))
os.makedirs(out, exist_ok=True)

sha1 = {f["id"]: next(h["value"] for h in f["hashes"] if h["algo"] == 1)
        for f in post("/mods/files", {"fileIds": [m["fileID"] for m in all_mods]})}
mr = modrinth(list(sha1.values()))

index = []  # (Pfad, metafile)
for m in all_mods:
    # CF-"Server" heißt nur "auf dem Server nötig", Einzelspieler braucht die Mods trotzdem
    side = "server" if m.get("serverPackOnly") else "client" if m["side"] == "client" else "both"
    rel = f'{FOLDER[m["classId"]]}/{m["slug"]}.pw.toml'
    os.makedirs(os.path.join(pack, os.path.dirname(rel)), exist_ok=True)
    h = sha1[m["fileID"]]
    if h in mr:
        url, mod_id, version = mr[h]
        download = f'url = {q(url)}\nhash-format = "sha1"\nhash = "{h}"\n'
        update = f'[update.modrinth]\nmod-id = {q(mod_id)}\nversion = {q(version)}\n'
    else:
        download = f'hash-format = "sha1"\nhash = "{h}"\nmode = "metadata:curseforge"\n'
        update = f'[update.curseforge]\nfile-id = {m["fileID"]}\nproject-id = {m["projectID"]}\n'
    with open(os.path.join(pack, rel), "w") as f:
        f.write(f'name = {q(m["name"])}\nfilename = {q(m["fileName"])}\nside = "{side}"\n\n'
                f'[download]\n{download}\n[update]\n{update}')
    index.append((rel, True))

for jar, (name, side) in sorted(EXTRA_MODS.items()):
    rel = f'mods/{jar.rsplit("-", 1)[0]}.pw.toml'
    h = hashlib.sha1(open(os.path.join(EXTRA_DIR, jar), "rb").read()).hexdigest()
    with open(os.path.join(pack, rel), "w") as f:
        f.write(f'name = {q(name)}\nfilename = {q(jar)}\nside = "{side}"\n\n'
                f'[download]\nurl = {q(f"{RAW_BASE}/extra-mods/{jar}")}\nhash-format = "sha1"\nhash = "{h}"\n')
    index.append((rel, True))

for rel, (name, side, project, version, filename, h) in sorted(MODRINTH_FILES.items()):
    url = f"https://cdn.modrinth.com/data/{project}/versions/{version}/{urllib.parse.quote(filename)}"
    os.makedirs(os.path.join(pack, os.path.dirname(rel)), exist_ok=True)
    with open(os.path.join(pack, rel), "w") as f:
        f.write(f'name = {q(name)}\nfilename = {q(filename)}\nside = "{side}"\n\n'
                f'[download]\nurl = {q(url)}\nhash-format = "sha1"\nhash = "{h}"\n\n'
                f'[update]\n[update.modrinth]\nmod-id = {q(project)}\nversion = {q(version)}\n')
    index.append((rel, True))

if os.path.isdir(server_overrides):
    for root, _, files in os.walk(server_overrides):
        for name in files:
            rel = os.path.relpath(os.path.join(root, name), server_overrides)
            os.makedirs(os.path.join(pack, os.path.dirname(rel)), exist_ok=True)
            shutil.copy2(os.path.join(root, name), os.path.join(pack, rel))

metafiles = {rel for rel, _ in index}
for root, _, files in os.walk(pack):
    for name in files:
        rel = os.path.relpath(os.path.join(root, name), pack).replace(os.sep, "/")
        if rel not in metafiles and rel not in ("index.toml", "pack.toml"):
            index.append((rel, False))

with open(os.path.join(pack, "index.toml"), "w") as f:
    f.write('hash-format = "sha256"\n')
    for rel, meta in sorted(index):
        f.write(f'\n[[files]]\nfile = {q(rel)}\nhash = "{sha256(os.path.join(pack, rel))}"\n'
                + ("metafile = true\n" if meta else "") + ("preserve = true\n" if rel in PRESERVE else ""))

with open(os.path.join(pack, "pack.toml"), "w") as f:
    f.write(f'name = {q(NAME)}\nauthor = {q(AUTHOR)}\nversion = {q(VERSION)}\npack-format = "packwiz:1.1.0"\n\n'
            f'[index]\nfile = "index.toml"\nhash-format = "sha256"\nhash = "{sha256(os.path.join(pack, "index.toml"))}"\n\n'
            f'[versions]\nminecraft = "{MC}"\nneoforge = "{NEOFORGE}"\n')

instance_cfg = f"""InstanceType=OneSix
name={NAME}
iconKey=default
OverrideCommands=true
PreLaunchCommand="$INST_JAVA" -jar packwiz-installer-bootstrap.jar {PACK_URL}
OverrideMemory=true
MinMemAlloc=4096
MaxMemAlloc=8192
"""
mmc_pack = {"formatVersion": 1, "components": [
    {"uid": "net.minecraft", "version": MC, "important": True},
    {"uid": "net.neoforged", "version": NEOFORGE},
]}

prism_zip = os.path.join(out, f"{SLUG}-Prism.zip")
with zipfile.ZipFile(prism_zip, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("instance.cfg", instance_cfg)
    z.writestr("mmc-pack.json", json.dumps(mmc_pack, indent=2))
    z.write(BOOTSTRAP, "minecraft/packwiz-installer-bootstrap.jar")
    z.writestr("minecraft/servers.dat", servers_dat(*SERVER))

manual = [m["slug"] for m in all_mods
          if not m.get("downloadUrl") and sha1[m["fileID"]] not in mr and not m.get("serverPackOnly")]
print(os.path.join(pack, "pack.toml"), f"{len(all_mods)} Mods ({len(mr)} von Modrinth) + {len(EXTRA_MODS)} eigene "
      f"+ {len(MODRINTH_FILES)} nur auf Modrinth, {len(index) - len(all_mods) - len(EXTRA_MODS) - len(MODRINTH_FILES)} weitere Dateien")
print(prism_zip, os.path.getsize(prism_zip))
print(f"manueller Download nötig (Drittanbieter-Downloads vom Autor gesperrt): {manual}")
