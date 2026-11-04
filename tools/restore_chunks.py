#!/usr/bin/env python3
"""Einzelne Chunks aus einer Backup-Welt in die aktuelle Welt zurückkopieren.

usage: restore_chunks.py <Weltordner> <Backup-Weltordner> <Auswahl.csv> <Sicherungsordner> [--apply] [--sub region,entities,poi]

Auswahl im MCA-Selector-Format (regionX;regionZ;chunkX;chunkZ, Chunk-Koordinaten lokal oder absolut). Standardmäßig
nur region/ (Blöcke, Block-Entities, Strukturdaten), Entities bleiben auf dem aktuellen Stand. Ohne --apply wird nur
angezeigt, was passieren würde. Mit --apply werden die betroffenen .mca-Dateien zuerst in den Sicherungsordner
kopiert, dann die Chunk-Daten aus dem Backup ans Ende der aktuellen Datei angehängt und der Dateikopf darauf
umgestellt (der alte Platz bleibt ungenutzt in der Datei). Ausgelagerte Riesen-Chunks (c.X.Z.mcc) werden mitkopiert.
Der Server muss dabei gestoppt sein (session.lock wird nicht geprüft).
"""
import os, shutil, sys, time
from collections import defaultdict


def main():
    world, backup_world, csv, safety = sys.argv[1:5]
    apply = "--apply" in sys.argv
    subs = sys.argv[sys.argv.index("--sub") + 1].split(",") if "--sub" in sys.argv else ["region"]
    sel = defaultdict(set)
    for line in open(csv):
        if line.strip():
            rx, rz, cx, cz = map(int, line.strip().split(";"))
            sel[(rx, rz)].add((cx & 31) + (cz & 31) * 32)
    now = int(time.time()).to_bytes(4, "big")
    total = missing = 0
    for sub in subs:
        for (rx, rz), idxs in sorted(sel.items()):
            name = f"r.{rx}.{rz}.mca"
            cur_path, bak_path = os.path.join(world, sub, name), os.path.join(backup_world, sub, name)
            if not os.path.exists(bak_path):
                print(f"{sub}/{name}: nicht im Backup, übersprungen")
                missing += len(idxs)
                continue
            bak = open(bak_path, "rb").read()
            cur = bytearray(open(cur_path, "rb").read()) if os.path.exists(cur_path) else bytearray(8192)
            if len(cur) % 4096:
                cur += b"\0" * (4096 - len(cur) % 4096)
            done = 0
            for i in sorted(idxs):
                entry = bak[i * 4:i * 4 + 4]
                if entry == b"\0\0\0\0":
                    missing += 1
                    continue
                off, count = int.from_bytes(entry[:3], "big") * 4096, entry[3]
                payload = bak[off:off + count * 4096]
                if bak[off + 4] & 0x80:  # Chunk liegt ausgelagert in c.X.Z.mcc
                    cx, cz = rx * 32 + i % 32, rz * 32 + i // 32
                    mcc = f"c.{cx}.{cz}.mcc"
                    if apply:
                        shutil.copy2(os.path.join(backup_world, sub, mcc), os.path.join(world, sub, mcc))
                pos = len(cur) // 4096
                cur += payload + b"\0" * (count * 4096 - len(payload))
                cur[i * 4:i * 4 + 4] = pos.to_bytes(3, "big") + bytes([count])
                cur[4096 + i * 4:4096 + i * 4 + 4] = now
                done += 1
            print(f"{sub}/{name}: {done} von {len(idxs)} Chunks aus dem Backup")
            total += done
            if not apply or not done:
                continue
            dst = os.path.join(safety, sub)
            os.makedirs(dst, exist_ok=True)
            if os.path.exists(cur_path):
                shutil.copy2(cur_path, os.path.join(dst, name))
            tmp = cur_path + ".restore-tmp"
            with open(tmp, "wb") as f:
                f.write(cur)
            os.replace(tmp, cur_path)
    print(f"{'Wiederhergestellt' if apply else 'Würde wiederherstellen'}: {total} Chunk-Einträge, nicht im Backup: {missing}"
          + (f", Sicherung in {safety}" if apply else ""))


if __name__ == "__main__":
    main()
