"""Look for answer lists that would confuse players. Prints a report and writes it to data/catalog-check.json.

Checks:
  1. the same piece listed twice under names in different languages (Studien / Études / Studies, Lied / Song ...)
  2. the same composer and catalog number (Op. 28 No. 4, S. 141 ...) under two different answers
  3. a set and one of its own pieces both offered in the search (players should pick the set, then the piece)
  4. a recording whose title has a number ("No. 2") but whose answer is a whole work with no set behind it
  5. near-identical titles by the same composer (spelling variants, typos)
Run: python3 tools/check_catalog.py   (exit code 0 even when it finds something; read the report)
"""
import json, re, unicodedata, collections, difflib, sys

cat = json.load(open("data/catalog.json", encoding="utf-8"))
def fold(s):
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
# the same word in English, French, German, Italian, Polish
SAME = [("etude", "etudes", "study", "studies", "studie", "studien", "studio", "studi", "etiuda"),
        ("prelude", "preludes", "praludium", "preludium", "preludio", "preambule"),
        ("waltz", "waltzes", "valse", "valses", "walzer", "valzer", "walc"),
        ("song", "songs", "lied", "lieder", "chanson", "chansons", "canzone", "melodie", "piesni", "piesn"),
        ("symphony", "symphonie", "sinfonie", "sinfonia", "symfonia"),
        ("concerto", "concert", "konzert", "koncert"),
        ("sonata", "sonate", "sonaten"), ("variations", "variationen", "variazioni", "wariacje"),
        ("march", "marche", "marsch", "marcia"), ("dance", "danse", "tanz", "danza", "dances", "tanze", "danses"),
        ("night", "nuit", "nacht", "notte"), ("without", "sans", "ohne", "senza"), ("words", "paroles", "worte", "parole"),
        ("caprice", "caprices", "capriccio", "capricci", "capricen", "kaprys"), ("fantasy", "fantasie", "fantaisie", "fantasia"),
        ("romance", "romanze", "romanza", "romans"), ("cradle", "berceuse", "wiegenlied", "ninna"), ("spring", "printemps", "fruhling", "primavera")]
CANON = {w: g[0] for g in SAME for w in g}
STOP = set("the a an and of in for de du des la le les et en to on op opus no nr major minor dur moll flat sharp piano for pour fur per from aus sur".split())
def words(title):
    t = re.sub(r"\b(op|opus|no|nr|s|bwv|k|d)\.?\s*\d+", " ", fold(title))
    t = re.sub(r"\b([a-g])(?:[\s-]*(flat|sharp))?[\s-]+(major|minor|dur|moll)\b", lambda m: f" key{m.group(1)}{m.group(2) or ''}{m.group(3)[:3]} ", t)
    return frozenset(CANON.get(w, w) for w in re.findall(r"[a-z]+", t) if w not in STOP and len(w) > 1)
def nums(title):
    f = fold(title)
    m = re.search(r"\b(op|opus|s|bwv|k|d|hob)\.?\s*(\d+)(?:[^0-9]{1,8}?(?:no|nr)\.?\s*(\d+))?", f)
    return (m.group(1).replace("opus", "op"), m.group(2), m.group(3) or "") if m else None

opts = [(n, k) for n, k in cat["pieceOptions"]]
game = {r["pieceKey"] for r in cat["recordings"]}
found = collections.defaultdict(list)
by_comp = collections.defaultdict(list)
for n, k in opts: by_comp[n.split(" – ")[0]].append((n, k))
for comp, items in by_comp.items():
    seen_w, seen_n = collections.defaultdict(list), collections.defaultdict(list)
    for n, k in items:
        t = n.split(" – ", 1)[1] if " – " in n else n
        w = words(t)
        if len(w) >= 1: seen_w[(w, re.sub(r"\D", "", t)[:6])].append((n, k))
        nm = nums(t)
        if nm: seen_n[nm].append((n, k))
    for group in seen_w.values():
        if len({k for _, k in group}) > 1 and any(k in game for _, k in group): found["same words, different answers (languages?)"].append([n for n, _ in group])
    for nm, group in seen_n.items():
        if len({k for _, k in group}) > 1 and any(k in game for _, k in group): found["same catalog number, different answers"].append([n for n, _ in group])
    titles = [(fold(n), n, k) for n, k in items if k in game]
    for fa, na, ka in titles:
        for fb, nb, kb in [(fold(n), n, k) for n, k in items]:
            if ka != kb and (fa, fb) == tuple(sorted((fa, fb))) and re.findall(r"\d+", fa) == re.findall(r"\d+", fb) and difflib.SequenceMatcher(None, fa, fb).ratio() > 0.92: found["near-identical titles"].append([na, nb])
listed = {k for _, k in opts}
for n, k in opts:      # an unnumbered single piece with the same catalog number as a set ("Impromptu, D. 899" next to "Four Impromptus, D. 899")
    nm = nums(n)
    if nm and not nm[2] and any(nums(n2) == nm and k2 != k and re.match(r"^(two|three|four|five|six|seven|eight|nine|ten|twelve|\d+)\b", fold(n2.split(" – ", 1)[-1])) for n2, k2 in by_comp[n.split(" – ")[0]]):
        found["single piece and a set share a catalog number"].append([n])
for sk, s in (cat.get("sets") or {}).items():
    shown = [n for n, k in s["members"] if k in listed]
    if shown: found["set and its own pieces both in the search"].append([s["name"]] + shown)
for r in cat["recordings"]:
    if r.get("set"): continue
    if re.search(r"\b(?:no|nr)\.?\s*\d+\s*$", fold(r.get("title") or "")) and not re.search(r"\d", r["piece"].split(" – ", 1)[-1]) and not r.get("movement"):
        found["numbered title, but the answer is a whole work"].append([r["id"], r.get("title"), r["piece"]])
report = {k: v for k, v in found.items()}
json.dump(report, open("data/catalog-check.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("Fix with data/same-piece.json ({\"name to drop\": \"name to keep\"}), data/label-fixes.json or data/overrides.json, then rebuild.")
for k, v in report.items():
    print(f"## {k}: {len(v)}")
    for x in v[:25]: print("  ", " | ".join(map(str, x)))
print("total findings:", sum(len(v) for v in report.values()))
