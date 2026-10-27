#!/usr/bin/env python3
"""Beim Docker-Build: deutsche Vanilla-Namen (block.*, item.*, entity.*) von Mojang nach lang_de_vanilla.json.
Schlägt der Download fehl, nimmt das Dashboard die Namen aus den Mods bzw. die englischen IDs."""
import json, sys, urllib.request

VERSION = sys.argv[1] if len(sys.argv) > 1 else "1.21.1"


def get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


try:
    manifest = get("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json")
    version = get(next(v["url"] for v in manifest["versions"] if v["id"] == VERSION))
    h = get(version["assetIndex"]["url"])["objects"]["minecraft/lang/de_de.json"]["hash"]
    de = get(f"https://resources.download.minecraft.net/{h[:2]}/{h}")
    keep = {k: v for k, v in de.items() if k.split(".")[0] in ("block", "item", "entity") and k.count(".") == 2}
    json.dump(keep, open("lang_de_vanilla.json", "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"{len(keep)} deutsche Namen für {VERSION}")
except Exception as e:
    print("Vanilla-Namen nicht geladen:", e)
