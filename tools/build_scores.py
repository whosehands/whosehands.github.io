"""Build the Guess the Score corpus: solo piano scores in Humdrum **kern, one file per piece or movement.

Sources (clone them first, then pass the folders):
  github.com/pl-wnifc/humdrum-chopin-first-editions   Chopin, first editions, CC BY 4.0 (The Fryderyk Chopin Institute)
  github.com/craigsapp/mozart-piano-sonatas           Mozart piano sonatas, CC BY-NC-SA 4.0 (Craig Stuart Sapp)
  github.com/craigsapp/haydn-piano-sonatas            Haydn piano sonatas, CC BY-NC-SA 4.0 (Craig Stuart Sapp)
Writes scores/<id>.krn (titles removed so the file doesn't give the answer away; license lines kept) and data/scores.json.
Run: python3 tools/build_scores.py CHOPIN_DIR MOZART_DIR HAYDN_DIR
"""
import glob, json, os, re, sys, collections

chopin_dir, mozart_dir, haydn_dir = sys.argv[1:4]
OUT = "scores"
os.makedirs(OUT, exist_ok=True)
for f in glob.glob(OUT + "/*.krn"): os.remove(f)

def ref(t, k):
    m = re.search(r"^!!!" + k + r":\s*(.*)$", t, re.M)
    return m.group(1).strip() if m else ""
def spines(t): return next((l.count("**kern") for l in t.splitlines() if l.startswith("**")), 0)
def measures(t): return len(re.findall(r"^=\d+", t, re.M)) or 1
def key_of(t):
    m = re.search(r"^\*([a-gA-G])([-#]?):", t, re.M)
    if not m: return ""
    n, acc = m.group(1), {"-": "-flat", "#": "-sharp", "": ""}[m.group(2)]
    return f"{n.upper()}{acc} {'minor' if n.islower() else 'major'}"
DROP = re.compile(r"^!!!(rism[^:]*|AFR|OCL|OTL|OTP|PTL|OPT|OPS|ONM|AGN|SCT\d?|COM|COA|OMV|PPR|PPP|PDT|AST|ODT|CDT|CNT|OPR|URL[^:]*|NIFC[^:]*|SEGMENT|!SEGMENT|EED|ENC|END|EST|YOR|YOY|YOO|YOE|OCY|ONB|system-decoration|filter|title|PED)[^\n]*\n", re.M)
def clean(t):
    t = re.sub(r"^!!!!SEGMENT[^\n]*\n", "", t, flags=re.M)
    t = DROP.sub("", t)
    t = re.sub(r"(?<![^\t\n])\*I[^\t\n]*", "*", t)        # instrument and section labels printed above the staff ("No. 4.")
    return re.sub(r"^!!LO:TX[^\n]*\n", "", t, flags=re.M)

items = []
def add(sid, composer, set_name, set_key, name, key, movement, text, source, license, attribution):
    body = clean(text)
    if "!!!YEM" not in body: body = f"!!!YEM: {license}. {attribution}\n" + body
    open(f"{OUT}/{sid}.krn", "w", encoding="utf-8").write(body)
    items.append({"id": sid, "composer": composer, "piece": name, "key": key, "set": set_key, "setName": set_name, "movement": movement,
                  "measures": measures(text), "source": source, "license": license, "by": attribution})

# --- Chopin: one edition per piece (the first file in the folder's order), solo piano only
FORM = {"Mazurka": ("Mazurka", "Mazurkas"), "Etude": ("Étude", "Études"), "Prelude": ("Prelude", "Preludes"), "Nocturne": ("Nocturne", "Nocturnes"),
        "Waltz": ("Waltz", "Waltzes"), "Polonaise": ("Polonaise", "Polonaises"), "Impromptu": ("Impromptu", "Impromptus"), "Ecossaise": ("Écossaise", "Écossaises"),
        "Scherzo": ("Scherzo", None), "Ballade": ("Ballade", None), "Rondo": ("Rondo", None), "Rondeau": ("Rondo", None), "Variations": ("Variations", None),
        "Fantasie": ("Fantaisie", None), "Bolero": ("Bolero", None), "Tarantelle": ("Tarantelle", None), "Allegro": ("Allegro de concert", None),
        "Berceuse": ("Berceuse", None), "Baracolle": ("Barcarolle", None), "Polonaise; Fantasie": ("Polonaise-Fantaisie", None),
        "Impromptu; Fantasie": ("Fantaisie-Impromptu", None), "March": ("Funeral March", None)}
SONATA = {"004": "Piano Sonata No. 1 in C minor, Op. 4", "035": "Piano Sonata No. 2 in B-flat minor, Op. 35", "058": "Piano Sonata No. 3 in B minor, Op. 58"}
KEYFIX = {("026", 1): "C-sharp minor", ("028", 1): "C major", ("028", 9): "E major", ("034", 2): "A minor", ("020", 0): "B minor",
          ("049", 0): "F minor", ("051", 0): "G-flat major", ("005", 0): "F major", ("016", 0): "E-flat major", ("046", 0): "A major",
          ("067", 1): "G major", ("067", 2): "G minor", ("067", 3): "C major", ("067", 4): "A minor", ("068", 1): "C major", ("068", 2): "A minor",
          ("068", 3): "F major", ("068", 4): "F minor", ("069", 1): "A-flat major", ("069", 2): "B minor", ("070", 1): "G-flat major", ("070", 2): "F minor",
          ("070", 3): "D-flat major", ("071", 1): "D minor", ("072", 2): "C minor", ("072", 3): "D major", ("072", 4): "G major", ("072", 5): "D-flat major",
          ("073", 0): "C major"}
SKIP = {"002", "003", "008", "011", "014", "021", "065", "074", "GDC", "MEG", "VGN"}
def ident_of(base):
    num = re.search(r"-(\d{3})(?:-[a-z-]+)?\.krn$", base) or re.match(r"^\d{3}_(\d+)-", base)
    return (base[:3], int(num.group(1)) if num else 0)
IDS = {ident_of(os.path.basename(g)) for g in glob.glob(os.path.join(chopin_dir, "kern", "*.krn"))}
seen = set()
for f in sorted(glob.glob(os.path.join(chopin_dir, "kern", "*.krn"))):
    base = os.path.basename(f)
    if re.search(r"-(violino|violoncello|violin|piano)\.krn$", base): continue
    op = base[:3]
    if op in SKIP or not op.isdigit(): continue
    t = open(f, encoding="utf-8", errors="replace").read()
    if spines(t) != 2: continue
    num = re.search(r"-(\d{3})(?:-[a-z-]+)?\.krn$", base) or re.match(r"^\d{3}_(\d+)-", base)
    n = int(num.group(1)) if num else 0
    ident = (op, n)
    if ident in seen: continue
    seen.add(ident)
    agn, opn = ref(t, "AGN"), str(int(op))
    key = KEYFIX.get((op, n), key_of(t))
    lic, by = "CC BY 4.0", "The Fryderyk Chopin Institute, Chopin's first editions (github.com/pl-wnifc/humdrum-chopin-first-editions)"
    if op in SONATA:
        add(f"chopin-op{opn}-{n}", "Chopin", None, None, "Chopin – " + SONATA[op], key, f"Movement {n}", t, base, lic, by); continue
    form, plural = FORM.get(agn, (agn or "Piece", None))
    numbered = n and plural and len({k for k in IDS if k[0] == op}) > 1
    if op == "072" and n == 0: continue   # a second copy of the Funeral March
    if op == "072":     # Op. 72: No. 1 Nocturne, No. 2 Funeral March, No. 3 Three Écossaises
        eco = form == "Écossaise"
        name = f"Chopin – {form} in {key}, Op. 72 " + (f"No. 3/{n - 2}" if eco else f"No. {n}")
        add(f"chopin-op72-{n}", "Chopin", "Chopin – Three Écossaises, Op. 72 No. 3" if eco else None, "chopin|op72|3" if eco else None, name, key, "", t, base, lic, by); continue
    if op == "071":
        add("chopin-op71-1", "Chopin", None, None, f"Chopin – Polonaise in {key}, Op. 71 No. 1", key, "", t, base, lic, by); continue
    if numbered:
        add(f"chopin-op{opn}-{n}", "Chopin", f"Chopin – {plural}, Op. {opn}", f"chopin|op{opn}|", f"Chopin – {form} in {key}, Op. {opn} No. {n}", key, "", t, base, lic, by)
    else:
        add(f"chopin-op{opn}", "Chopin", None, None, f"Chopin – {form}" + (f" in {key}" if key and form not in ('Variations', 'Funeral March') else "") + f", Op. {opn}", key, "", t, base, lic, by)

# --- Mozart and Haydn: every movement; the answer is the sonata
def sonatas(folder, composer, idp, catalog_ref, by):
    for f in sorted(glob.glob(os.path.join(folder, "kern", "*.krn"))):
        t = open(f, encoding="utf-8", errors="replace").read()
        if spines(t) != 2: continue
        title, cat_no, mv = ref(t, "OTL"), ref(t, catalog_ref), ref(t, "OMV") or "1"
        cat_no = re.sub(r"<[^>]+>", "", cat_no).replace("K1 ", "K. ").replace("K ", "K. ").strip()
        if composer == "Mozart" and not cat_no: cat_no = {"14": "K. 457", "17": "K. 576"}.get(re.sub(r"\D", "", title.split(" in ")[0]), "")
        m = re.match(r"(?:Piano\s+)?Sonata\s+No\.\s*(\d+)\s+in\s+(.+)$", title)
        if not m: continue
        name = f"{composer} – Piano Sonata No. {m.group(1)} in {m.group(2)}, {cat_no}" if composer == "Mozart" else f"{composer} – Piano Sonata in {m.group(2)}, {cat_no}"
        sid = f"{idp}-{os.path.basename(f)[:-4]}"
        add(sid, composer, None, None, name, key_of(t), f"Movement {mv}", t, os.path.basename(f), "CC BY-NC-SA 4.0", by)
sonatas(mozart_dir, "Mozart", "mozart", "SCT1", "Craig Stuart Sapp, Mozart piano sonatas (github.com/craigsapp/mozart-piano-sonatas)")
sonatas(haydn_dir, "Haydn", "haydn", "SCT", "Craig Stuart Sapp, Haydn piano sonatas (github.com/craigsapp/haydn-piano-sonatas)")

for it in items: it["answerKey"] = re.sub(r"[^a-z0-9]+", "-", it["piece"].lower()).strip("-")
sets = collections.defaultdict(list)
for it in items:
    if it["set"]: sets[it["set"]].append([it["piece"], it["answerKey"]])
out = {"pieces": items, "sets": {k: {"name": next(i["setName"] for i in items if i["set"] == k), "members": sorted(v, key=lambda x: int(re.search(r"(\d+)$", x[0]).group(1)) if re.search(r"(\d+)$", x[0]) else 0)} for k, v in sets.items()}}
json.dump(out, open("data/scores.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(items), "scores;", len({i["piece"] for i in items}), "distinct answers;", len(sets), "sets;", collections.Counter(i["composer"] for i in items))
