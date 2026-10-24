#!/usr/bin/env python3
"""Farmer's Delight und Let's Do Farm & Charm verbinden: Datapack-Dateien für kubejs/data erzeugen.

usage: farmcharm_compat.py <Ordner mit Mod-Jars> <packwiz/kubejs/data>

Eine fertige Compat-Mod gibt es für NeoForge 1.21.1 nicht (Let's Do Delight nur Fabric 1.20.1, Let's Do Addon
Compat nur Kochtopf-Rezepte). Der Ordner mit den Jars ist z. B. der mods/-Ordner eines Testservers.

- Schneidebretter: Messer-Rezepte des Farmer's-Delight-Bretts gibt es auch auf dem Farm-&-Charm-Brett und
  umgekehrt (data/proudmountain/recipe/farmcharm_compat/). Übersprungen, wenn das Ziel-Brett für die Zutat schon
  ein Rezept hat. Das F&C-Brett kann nur mit Messern schneiden und kennt keine Zufallsdrops: Rezepte für Axt,
  Hacke, Spitzhacke, Schere usw. bleiben beim FD-Brett, Drops mit chance < 1 entfallen auf dem F&C-Brett.
  Die Zusammenbau-Rezepte (cutting_board_assembly) gehen nur auf dem F&C-Brett.
- Doppelte Zutaten (SAME) sind austauschbar: Tag proudmountain:compat/<name> mit beiden Items. Rezepte, die eines
  davon als festes Item verlangen, werden mit dem Tag überschrieben (data/<ns>/recipe/<pfad>.json); Tags, die in
  Rezepten benutzt werden und nur eine Fassung enthalten, bekommen die andere dazu. Würden dadurch zwei Rezepte
  derselben Art dieselbe Eingabe haben (z. B. Ofen: FD-Speck und F&C-Speck), bleiben sie unverändert.
- EXTRA_TAGS: einzelne Tag-Ergänzungen (Brotmesser als Messer, Salat als Blattgemüse).

Alle erzeugten Dateien stehen in tools/farmcharm_compat.generated und werden beim nächsten Lauf zuerst gelöscht.
"""
import collections, glob, json, os, re, sys, zipfile

SAME = {
    "onion": ("farmersdelight:onion", "farm_and_charm:onion"),
    "tomato": ("farmersdelight:tomato", "farm_and_charm:tomato"),
    "tomato_seeds": ("farmersdelight:tomato_seeds", "farm_and_charm:tomato_seeds"),
    "rotten_tomato": ("farmersdelight:rotten_tomato", "farm_and_charm:rotten_tomato"),
    "bacon": ("farmersdelight:bacon", "farm_and_charm:bacon"),
    "cooked_bacon": ("farmersdelight:cooked_bacon", "farm_and_charm:cooked_bacon"),
    "minced_beef": ("farmersdelight:minced_beef", "farm_and_charm:minced_beef"),
    "raw_pasta": ("farmersdelight:raw_pasta", "farm_and_charm:raw_pasta"),
    "dough": ("farmersdelight:wheat_dough", "farm_and_charm:dough"),
    "chicken_cuts": ("farmersdelight:chicken_cuts", "farm_and_charm:chicken_parts"),
    "cooked_chicken_cuts": ("farmersdelight:cooked_chicken_cuts", "farm_and_charm:cooked_chicken_parts"),
}
EXTRA_TAGS = {
    "c:tools/knife": ["bakery:bread_knife"],  # steht nur in farmersdelight:tools/knives, beide Bretter prüfen c:tools/knife
    "c:foods/leafy_green": ["farm_and_charm:lettuce"],  # Sandwiches, Salate und Suppen von Farmer's Delight
}
FD_CUT, FC_CUT = "farmersdelight:cutting", "farm_and_charm:cutting_board"
KNIFE = "c:tools/knife"
# Ingredient-Felder, die keine Zutaten sind (Ergebnisse, Item-Stacks)
NOT_INGREDIENT = {"result", "results", "output", "outputs", "byproducts", "providers", "container"}
# Rezepttypen, bei denen dieselbe Eingabe nur ein Ergebnis haben kann (eine Zutat, ein Rezept)
SINGLE_INPUT = {"minecraft:smelting", "minecraft:smoking", "minecraft:blasting", "minecraft:campfire_cooking",
                FD_CUT, FC_CUT, "farm_and_charm:mincer", "farm_and_charm:drying"}
SKIP_TYPES = {"jeed:effect_provider"}  # "item" sind dort Item-Stacks, keine Zutaten
MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "farmcharm_compat.generated")
TAG_PREFIX = "proudmountain:compat/"


def norm(t):
    return t if ":" in t else "minecraft:" + t


class Pack:
    def __init__(self, jars):
        self.tags, self.recipes, self.mods = collections.defaultdict(list), {}, {"minecraft", "c", "neoforge"}
        for j in sorted(jars):
            z = zipfile.ZipFile(j)
            for n in z.namelist():
                if n.endswith("mods.toml"):
                    self.mods |= set(re.findall(r'modId\s*=\s*"([^"]+)"', z.read(n).decode("utf-8", "replace")))
                m = re.match(r"data/([^/]+)/tags/item/(.+)\.json$", n)
                if m:
                    try:
                        d = json.loads(z.read(n))
                    except Exception:
                        continue
                    if d.get("replace"):
                        self.tags[f"{m[1]}:{m[2]}"] = []
                    self.tags[f"{m[1]}:{m[2]}"] += [v["id"] if isinstance(v, dict) else v for v in d.get("values", [])]
                m = re.match(r"data/([^/]+)/recipe/(.+)\.json$", n)
                if m:
                    try:
                        self.recipes[f"{m[1]}:{m[2]}"] = json.loads(z.read(n))
                    except Exception:
                        pass
        self.cache = {}

    def resolve(self, tag, seen=()):
        if tag in self.cache:
            return self.cache[tag]
        out = set()
        for v in self.tags.get(tag, ()):
            if v.startswith("#"):
                if v[1:] not in seen:
                    out |= self.resolve(v[1:], seen + (tag,))
            else:
                out.add(v)
        if not seen:
            self.cache[tag] = frozenset(out)
        return frozenset(out)

    def items(self, ing):
        """Menge der Items, die eine Zutat (dict oder Liste von dicts) annimmt."""
        if isinstance(ing, list):
            return frozenset().union(*[self.items(i) for i in ing]) if ing else frozenset()
        if "item" in ing and isinstance(ing["item"], str):
            return frozenset([ing["item"]])
        if "tag" in ing:
            return self.resolve(ing["tag"])
        return frozenset()


def is_ingredient(o):
    return isinstance(o, dict) and (isinstance(o.get("item"), str) or isinstance(o.get("tag"), str)) and \
        not {"count", "id"} & set(o)


def ingredients(o, out=None):
    """Alle Zutaten-Objekte eines Rezepts (ohne Ergebnis-Felder)."""
    out = [] if out is None else out
    if is_ingredient(o):
        out.append(o)
    elif isinstance(o, dict):
        for k, v in o.items():
            if k not in NOT_INGREDIENT and k != "neoforge:conditions":
                ingredients(v, out)
    elif isinstance(o, list):
        for v in o:
            ingredients(v, out)
    return out


def input_key(pack, r):
    """Vergleichsschlüssel der Eingabe: gleiche Schlüssel (bzw. überlappende Items bei SINGLE_INPUT) = Konflikt."""
    t = norm(r.get("type", ""))
    if t in SINGLE_INPUT:
        ings = ingredients({k: v for k, v in r.items() if k in ("ingredient", "ingredients")})
        return t, pack.items(ings)
    if t == "minecraft:crafting_shaped":
        key = {c: pack.items(v) for c, v in r.get("key", {}).items()}
        return t, tuple(tuple(key.get(c, frozenset()) for c in row) for row in r.get("pattern", []))
    return t, tuple(sorted((tuple(sorted(pack.items(i))) for i in ingredients(r))))


def conflict_pairs(pack, state):
    """Paare von Rezepten desselben Typs, deren Eingabe sich überschneidet (SINGLE_INPUT) bzw. gleich ist."""
    groups = collections.defaultdict(lambda: collections.defaultdict(set))
    for rid, r in state.items():
        t, k = input_key(pack, r)
        for i in (k if t in SINGLE_INPUT else [k]):
            groups[t][i].add(rid)
    return {(a, b) for g in groups.values() for s in g.values() for a in s for b in s if a < b}


def rewrite(o, swap):
    """Festes Item einer doppelten Zutat durch den gemeinsamen Tag ersetzen. Gibt (neues Objekt, geändert) zurück."""
    if is_ingredient(o) and o.get("item") in swap:
        return {"tag": swap[o["item"]]}, True
    if isinstance(o, dict):
        changed, new = False, {}
        for k, v in o.items():
            if k in NOT_INGREDIENT or k == "neoforge:conditions":
                new[k] = v
                continue
            new[k], c = rewrite(v, swap)
            changed |= c
        return new, changed
    if isinstance(o, list):
        res = [rewrite(v, swap) for v in o]
        return [v for v, _ in res], any(c for _, c in res)
    return o, False


def fd_to_fc(r):
    """Messer-Rezept des FD-Bretts als F&C-Rezept, sonst None."""
    tools = r["tool"] if isinstance(r["tool"], list) else [r["tool"]]
    if not any(t.get("tag") == KNIFE for t in tools) or len(r["ingredients"]) != 1:
        return None
    sure = [x["item"] for x in r["result"] if x.get("chance", 1) >= 1]
    if not sure:
        return None
    out = {"type": FC_CUT, "ingredient": r["ingredients"][0], "result": sure[0], "experience": 0.1}
    if sure[1:]:
        out["byproducts"] = sure[1:]
    return out


def fc_to_fd(r):
    res = [r["result"]] + r.get("byproducts", [])
    return {"type": FD_CUT, "ingredients": [r["ingredient"]], "tool": {"tag": KNIFE},
            "result": [{"item": x} for x in res]}


def main():
    jars, out = sys.argv[1], sys.argv[2]
    pack = Pack(glob.glob(os.path.join(jars, "*.jar")))
    files = {}  # Pfad relativ zu out -> Inhalt

    def loaded(rid, r):
        t = norm(r.get("type", ""))
        return t.split(":")[0] in pack.mods and t not in SKIP_TYPES and not rid.startswith("proudmountain:")

    # 1. gemeinsame Tags
    swap = {}
    for name, items in SAME.items():
        missing = [i for i in items if i.split(":")[0] not in pack.mods]
        if missing:
            sys.exit(f"Mod fehlt für {missing}")
        files[f"proudmountain/tags/item/compat/{name}.json"] = {"replace": False, "values": list(items)}
        pack.tags[TAG_PREFIX + name] = list(items)
        swap.update({i: TAG_PREFIX + name for i in items})

    # 2. Schneidebretter spiegeln
    recipes = {rid: r for rid, r in pack.recipes.items() if loaded(rid, r)}
    by_type = collections.defaultdict(list)
    for rid, r in recipes.items():
        by_type[norm(r.get("type", ""))].append((rid, r))
    partner = {a: b for a, b in SAME.values()} | {b: a for a, b in SAME.values()}

    def equiv(items):  # doppelte Zutaten zählen als dieselbe
        return set(items) | {partner[i] for i in items if i in partner}

    mirrored = collections.Counter()
    for src, dst, conv in ((FD_CUT, FC_CUT, fd_to_fc), (FC_CUT, FD_CUT, fc_to_fd)):
        taken = equiv(set().union(*[input_key(pack, r)[1] for _, r in by_type[dst]]))
        for rid, r in sorted(by_type[src]):
            new = conv(r)
            if new is None:
                continue
            got = equiv(input_key(pack, new)[1])
            if not got or got & taken:
                continue
            taken |= got
            new, _ = rewrite(new, swap)
            ns, path = rid.split(":")
            files[f"proudmountain/recipe/farmcharm_compat/{dst.split(':')[0]}/{ns}/{path.split('/')[-1]}.json"] = new
            mirrored[dst] += 1

    # 3. feste Items durch gemeinsame Tags ersetzen, ohne neue Eingabe-Konflikte
    candidates = {}
    for rid, r in recipes.items():
        new, changed = rewrite(r, swap)
        if changed:
            candidates[rid] = new
    old_pairs = conflict_pairs(pack, recipes)
    state = dict(recipes)
    state.update(candidates)
    reverted = set()
    while True:
        bad = {x for p in conflict_pairs(pack, state) - old_pairs for x in p} & set(candidates) - reverted
        if not bad:
            break
        for rid in bad:
            state[rid] = recipes[rid]
        reverted |= bad
    for rid, new in candidates.items():
        if rid not in reverted:
            ns, path = rid.split(":")
            files[f"{ns}/recipe/{path}.json"] = new

    # 1:1-Umwandlung im Crafting-Grid für das, was danach noch an einer Fassung hängt (Ofen, Kisten, Säcke)
    single = set()  # Items, die schon ein Crafting-Rezept mit genau einer Zutat haben
    for r in state.values():
        t = norm(r.get("type", ""))
        if t == "minecraft:crafting_shapeless" and len(r.get("ingredients", [])) == 1:
            single |= pack.items(r["ingredients"][0])
        elif t == "minecraft:crafting_shaped" and "".join(r.get("pattern", [])).strip() in r.get("key", {}):
            single |= pack.items(r["key"]["".join(r["pattern"]).strip()])
    converted = 0
    for name, (a, b) in SAME.items():
        for x, y in ((a, b), (b, a)):
            conv = {"type": "minecraft:crafting_shapeless", "category": "misc", "ingredients": [{"item": x}],
                    "result": {"id": y, "count": 1}}
            rid = f"proudmountain:farmcharm_compat/convert/{x.replace(':', '_')}"
            if x in single:
                continue
            state[rid] = conv
            files[f"proudmountain/recipe/farmcharm_compat/convert/{x.replace(':', '_')}.json"] = conv
            converted += 1

    # 4. Tags in Rezepten um die jeweils andere Fassung ergänzen
    used = set()
    for rid, r in state.items():
        used |= {i["tag"] for i in ingredients(r) if "tag" in i and not i["tag"].startswith(TAG_PREFIX)}
    additions = collections.defaultdict(set)
    for tag in sorted(used):
        got = pack.resolve(tag)
        for a, b in SAME.values():
            if (a in got) != (b in got):
                additions[tag].add(b if a in got else a)
    for tag, items in EXTRA_TAGS.items():
        additions[tag] |= set(items)
    for tag, items in additions.items():
        ns, path = tag.split(":")
        files[f"{ns}/tags/item/{path}.json"] = {"replace": False, "values": sorted(items)}

    # Abschlussprüfung mit allen Änderungen: neue Überschneidungen melden (z. B. durch Tag-Ergänzungen)
    final = dict(state)
    for p, d in files.items():
        if "/recipe/" in p and p.startswith("proudmountain/"):
            final["proudmountain:" + p.split("/recipe/", 1)[1][:-5]] = d
    orig_pairs = conflict_pairs(pack, recipes)
    for tag, items in additions.items():
        pack.tags[tag] = pack.tags[tag] + sorted(items)
    pack.cache.clear()
    new_pairs = sorted(conflict_pairs(pack, final) - orig_pairs)

    # schreiben: alte erzeugte Dateien weg, keine handgepflegten überschreiben
    old = open(MANIFEST).read().split() if os.path.exists(MANIFEST) else []
    for p in old:
        if os.path.exists(os.path.join(out, p)):
            os.remove(os.path.join(out, p))
    clash = [p for p in files if os.path.exists(os.path.join(out, p))]
    if clash:
        sys.exit(f"existiert schon (nicht von diesem Skript): {clash}")
    for p, d in files.items():
        full = os.path.join(out, p)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
            f.write("\n")
    for p in old:  # leere Ordner aufräumen
        d = os.path.dirname(os.path.join(out, p))
        while d != out and os.path.isdir(d) and not os.listdir(d):
            os.rmdir(d)
            d = os.path.dirname(d)
    open(MANIFEST, "w").write("\n".join(sorted(files)) + "\n")
    print(f"gespiegelt: {dict(mirrored)}; Rezepte mit gemeinsamen Tags: {len(candidates) - len(reverted)} "
          f"(unverändert wegen Konflikt: {len(reverted)}); Umwandlungen: {converted}; Tag-Ergänzungen: {len(additions)}; "
          f"Dateien: {len(files)}", file=sys.stderr)
    for rid in sorted(reverted):
        print("  Konflikt, unverändert:", rid, file=sys.stderr)
    for a, b in new_pairs:
        print("  neue Überschneidung:", a, b, file=sys.stderr)


if __name__ == "__main__":
    main()
