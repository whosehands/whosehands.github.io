"""Build the Guess the Score corpus: one file per piece or movement.

Sources (clone them first, then pass the folders):
  github.com/pl-wnifc/humdrum-chopin-first-editions   Chopin, first editions, CC BY 4.0 (The Fryderyk Chopin Institute)
  github.com/craigsapp/mozart-piano-sonatas           Mozart piano sonatas, CC BY-NC-SA 4.0 (Craig Stuart Sapp)
  github.com/craigsapp/haydn-piano-sonatas            Haydn piano sonatas, CC BY-NC-SA 4.0 (Craig Stuart Sapp)
  OPEN_DIR, a folder holding clones of:
    github.com/OpenScore/Lieder, github.com/OpenScore/StringQuartets                     CC0
    github.com/DCMLab/<name> for each name in DCML below (Distant Listening Corpus)      CC BY-NC-SA 4.0
The OpenScore and DCML files are MuseScore files; MuseScore 3 converts them to MusicXML (set MSCORE to its command,
e.g. "xvfb-run -a /path/to/AppRun"). Titles and credits are removed (lyrics stay) so the file doesn't give the answer away.
Copyright: only works by composers who died by 1930 (public domain in the US and EU), or with a known date of 1930 or
earlier by composers who died by 1955.
Writes scores/<id>.krn or scores/<id>.mxl and data/scores.json.
Run: MSCORE=... python3 tools/build_scores.py CHOPIN_DIR MOZART_DIR HAYDN_DIR OPEN_DIR
"""
import glob, json, os, re, sys, collections, subprocess, zipfile, hashlib, csv, unicodedata, shlex

chopin_dir, mozart_dir, haydn_dir, open_dir = sys.argv[1:5]
OUT = "scores"
os.makedirs(OUT, exist_ok=True)
for f in glob.glob(OUT + "/*.krn") + glob.glob(OUT + "/*.mxl"): os.remove(f)

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
def add(sid, composer, set_name, set_key, name, key, movement, text, source, license, attribution, genre=""):
    body = clean(text)
    if "!!!YEM" not in body: body = f"!!!YEM: {license}. {attribution}\n" + body
    open(f"{OUT}/{sid}.krn", "w", encoding="utf-8").write(body)
    items.append({"id": sid, "file": f"{OUT}/{sid}.krn", "genre": genre or ("Piano sonata" if "Sonata" in name else ""), "composer": composer, "piece": name, "key": key, "set": set_key, "setName": set_name, "movement": movement,
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
        add(f"chopin-op{opn}-{n}", "Chopin", f"Chopin – {plural}, Op. {opn}", f"chopin|op{opn}|", f"Chopin – {form} in {key}, Op. {opn} No. {n}", key, "", t, base, lic, by, form)
    else:
        add(f"chopin-op{opn}", "Chopin", None, None, f"Chopin – {form}" + (f" in {key}" if key and form not in ('Variations', 'Funeral March') else "") + f", Op. {opn}", key, "", t, base, lic, by, form)

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

# --- OpenScore and DCML: MuseScore files, converted to MusicXML
def fold(x): return "".join(c for c in unicodedata.normalize("NFD", x) if unicodedata.category(c) != "Mn").lower()
def yaml_people(path):
    """the composers.yaml files (StrictYAML; flat enough to read by hand): folder name -> (name, died)"""
    out, cur = {}, {}
    for line in open(path, encoding="utf-8"):
        m = re.match(r"^  (\w+): (.*)$", line)
        if re.match(r"^\S", line) and cur.get("path"): out[cur["path"]] = cur; cur = {}
        if m: cur[m.group(1)] = m.group(2).strip()
    if cur.get("path"): out[cur["path"]] = cur
    return out
SURNAME = {"Ludwig van Beethoven": "Beethoven", "Johann Sebastian Bach": "J. S. Bach", "Carl Philipp Emanuel Bach": "C. P. E. Bach",
           "Johann Christian Bach": "J. C. Bach", "Wilhelm Friedemann Bach": "W. F. Bach", "Georg Friedrich Händel": "Handel",
           "Clara Schumann": "Clara Schumann", "Pyotr Ilyich Tchaikovsky": "Tchaikovsky", "Jan Pieterszoon Sweelinck": "Sweelinck"}
KEYNAME = lambda k: "" if not k or k == "None" else (k[0].upper() + {"b": "-flat", "#": "-sharp"}.get(k[1:2], "") + (" minor" if k[0].islower() else " major"))
def opus(x):
    x = (x or "").strip()
    x = re.sub(r"(?i)\bop\.?\s*(\d+)\s*/\s*(\d+)", r"Op. \1 No. \2", x)
    x = re.sub(r"(?i)\bop\.?\s*(\d+)", r"Op. \1", x)
    x = re.sub(r"(?i)\bno\.?\s*(\d+)", r"No. \1", x)
    return x
pending = []      # (id, mscx path, item)
GENRE = {"beethoven_piano_sonatas": "Piano sonata", "ABC": "String quartet", "bach_en_fr_suites": "Keyboard suite", "bach_solo": "Piece for solo violin or cello",
         "corelli": "Trio sonata", "cpe_bach_keyboard": "Keyboard piece", "jc_bach_sonatas": "Keyboard sonata", "kozeluh_sonatas": "Keyboard sonata",
         "mendelssohn_quartets": "String quartet", "pleyel_quartets": "String quartet", "wf_bach_sonatas": "Keyboard sonata", "sweelinck_keyboard": "Keyboard fantasia",
         "handel_keyboard": "Keyboard suite", "debussy_suite_bergamasque": "Piano suite", "bartok_bagatelles": "Piano miniature", "c_schumann_lieder": "Song for voice and piano",
         "couperin_clavecin": "Harpsichord prelude", "dvorak_silhouettes": "Piano miniature", "grieg_lyric_pieces": "Piano miniature", "liszt_pelerinage": "Piano piece",
         "mahler_kindertotenlieder": "Song for voice and orchestra (piano version)", "schubert_winterreise": "Song for voice and piano", "schumann_kinderszenen": "Piano miniature",
         "schumann_liederkreis": "Song for voice and piano", "tchaikovsky_seasons": "Piano piece", "ravel_piano": "Piano piece", "debussy_preludes": "Piano prelude",
         "rachmaninoff_piano": "Piano variations", "Lieder": "Song for voice and piano", "StringQuartets": "String quartet"}
DCML_LANG = {"c_schumann_lieder": "German", "mahler_kindertotenlieder": "German", "schubert_winterreise": "German", "schumann_liederkreis": "German"}
DCML_WORDS = {"mahler_kindertotenlieder": "Friedrich Rückert", "schubert_winterreise": "Wilhelm Müller", "schumann_liederkreis": "Joseph von Eichendorff"}
def add_ms(sid, src, composer, name, set_name, set_key, movement, key, license, by, order=0, genre="", year=0):
    pending.append((sid, src, {"id": sid, "genre": genre, "year": year, "file": f"{OUT}/{sid}.mxl", "composer": composer, "piece": name, "key": key, "set": set_key,
                                "setName": set_name, "movement": movement, "order": order, "source": os.path.relpath(src, open_dir), "license": license, "by": by}))
def sid_of(prefix, path): return prefix + "-" + hashlib.md5(path.encode()).hexdigest()[:10]

# DCML corpora: which ones are sets of separate pieces (guess the set, then the piece) and which are works in movements
DCML = {"beethoven_piano_sonatas": "work", "ABC": "work", "bach_en_fr_suites": "work", "bach_solo": "work", "corelli": "work", "cpe_bach_keyboard": "work",
        "jc_bach_sonatas": "work", "kozeluh_sonatas": "work", "mendelssohn_quartets": "work", "pleyel_quartets": "work", "wf_bach_sonatas": "work",
        "sweelinck_keyboard": "work", "handel_keyboard": "work", "debussy_suite_bergamasque": "set", "bartok_bagatelles": "set", "c_schumann_lieder": "set",
        "couperin_clavecin": "set", "dvorak_silhouettes": "set", "grieg_lyric_pieces": "set", "liszt_pelerinage": "set", "mahler_kindertotenlieder": "set",
        "schubert_winterreise": "set", "schumann_kinderszenen": "set", "schumann_liederkreis": "set", "tchaikovsky_seasons": "set", "ravel_piano": "set",
        "debussy_preludes": "set", "rachmaninoff_piano": "set"}
DEBUSSY = {"l117": ("Préludes, Book 1", ["Danseuses de Delphes", "Voiles", "Le vent dans la plaine", "Les sons et les parfums tournent dans l'air du soir", "Les collines d'Anacapri",
           "Des pas sur la neige", "Ce qu'a vu le vent d'ouest", "La fille aux cheveux de lin", "La sérénade interrompue", "La cathédrale engloutie", "La danse de Puck", "Minstrels"]),
           "l123": ("Préludes, Book 2", ["Brouillards", "Feuilles mortes", "La puerta del Vino", "Les fées sont d'exquises danseuses", "Bruyères", "General Lavine – eccentric",
           "La terrasse des audiences du clair de lune", "Ondine", "Hommage à S. Pickwick Esq. P.P.M.P.C.", "Canope", "Les tierces alternées", "Feux d'artifice"])}
DCML_BY = "Distant Listening Corpus, Digital and Cognitive Musicology Lab, EPFL (github.com/DCMLab/{})"
for repo, kind in DCML.items():
    meta = os.path.join(open_dir, repo, "metadata.tsv")
    if not os.path.exists(meta): print("missing", repo); continue
    rows = list(csv.DictReader(open(meta, encoding="utf-8"), delimiter="\t"))
    first_key = {}
    for r in rows:
        if (r.get("movementNumber") or "1").strip() in ("1", ""): first_key.setdefault((r.get("workTitle"), r.get("workNumber")), r.get("annotated_key"))
    for r in rows:
        src = os.path.join(open_dir, repo, r["rel_path"])
        if not os.path.exists(src): continue
        try: year = int(r.get("composed_end") or 0)
        except ValueError: year = 0
        if year > 1930: continue                                   # e.g. Rachmaninoff's Corelli Variations (1931)
        full = (r.get("composer") or "").strip() or {"debussy_preludes": "Claude Debussy"}.get(repo, "")
        comp = SURNAME.get(full, full.split()[-1] if full else "")
        wt, wn, mv, mt = (r.get("workTitle") or "").strip(), opus(r.get("workNumber")), (r.get("movementNumber") or "").strip(), (r.get("movementTitle") or "").strip()
        key = KEYNAME(first_key.get((r.get("workTitle"), r.get("workNumber"))) or r.get("annotated_key"))
        by, lic = DCML_BY.format(repo), "CC BY-NC-SA 4.0"
        sid = sid_of("dcml", src)
        if repo == "ABC":                                          # Beethoven string quartets: names from the file name
            m = re.match(r"n(\d+)op(\d+)(?:-(\d+))?_(\d+)", r["piece"])
            if not m: continue
            num, op_, sub, mvn = m.groups()
            k1 = KEYNAME(next((x.get("annotated_key") for x in rows if x["piece"].startswith(r["piece"].split("_")[0] + "_01")), ""))
            name = f"Beethoven – String Quartet No. {int(num)} in {k1}, Op. {op_}" + (f" No. {sub}" if sub else "")
            add_ms(sid, src, "Beethoven", name, None, None, f"Movement {int(mvn)}", k1, lic, by, 0, GENRE[repo], year); continue
        if repo == "debussy_preludes":
            m = re.search(r"(l117|l123)-(\d+)", r["rel_path"])
            if not m: continue
            book, titles = DEBUSSY[m.group(1)]
            n = int(m.group(2))
            add_ms(sid, src, "Debussy", f"Debussy – {titles[n - 1]}", f"Debussy – {book}", f"debussy|{m.group(1)}", "", "", lic, by, n, GENRE[repo], year); continue
        if repo == "beethoven_piano_sonatas":
            wt = wt.replace("Sonata no.", "Piano Sonata No.")
        title = wt + (f" in {key}" if key and " in " not in wt and kind == "work" and not re.search(r"(?i)suite|variation|fantasia", wt) else "") + (f", {wn}" if wn and wn not in wt else "")
        if kind == "work" or not mt:
            add_ms(sid, src, comp, f"{comp} – {title}", None, None, (f"Movement {mv}" + (f": {mt}" if mt else "")) if mv else mt, key, lic, by, 0, GENRE[repo], year)
        else:
            member = re.sub(r"^\d+\.\s*", "", mt)
            add_ms(sid, src, comp, f"{comp} – {member}", f"{comp} – {title}", f"{fold(comp)}|{fold(title)}", "", KEYNAME(r.get("annotated_key")), lic, by, int(mv) if mv.isdigit() else 0, GENRE[repo], year)
            pending[-1][2].update({k: v for k, v in (("language", DCML_LANG.get(repo)), ("words", DCML_WORDS.get(repo) or (r.get("lyricist") or r.get("poet") or "").strip())) if v})

# OpenScore Lieder and String Quartets
def yaml_scores(path):
    """scores.yaml: score path -> {lyricist, language}"""
    out, cur = {}, {}
    if not os.path.exists(path): return out
    for line in open(path, encoding="utf-8"):
        m = re.match(r"^  (\w+): (.*)$", line)
        if re.match(r"^\S", line) and cur.get("path"): out[cur["path"]] = cur; cur = {}
        if m: cur[m.group(1)] = m.group(2).strip().strip("'\"")
    if cur.get("path"): out[cur["path"]] = cur
    return out
LANG = {"DE": "German", "EN": "English", "FR": "French", "IT": "Italian", "ES": "Spanish", "NO": "Norwegian", "SV": "Swedish", "DA": "Danish", "RU": "Russian",
        "CS": "Czech", "PL": "Polish", "NL": "Dutch", "HU": "Hungarian", "FI": "Finnish", "LA": "Latin", "PT": "Portuguese", "CA": "Catalan"}
def openscore(folder, prefix, label):
    people = yaml_people(os.path.join(open_dir, folder, "data", "composers.yaml"))
    smeta = yaml_scores(os.path.join(open_dir, folder, "data", "scores.yaml"))
    names = {p: v.get("name", p) for p, v in people.items()}
    surn = collections.Counter(n.split()[-1] for n in names.values())
    for src in sorted(glob.glob(os.path.join(open_dir, folder, "scores", "**", "*.mscx"), recursive=True)):
        parts = os.path.relpath(src, os.path.join(open_dir, folder, "scores")).split(os.sep)
        who = people.get(parts[0], {})
        try: died = int(who.get("died", "9999"))
        except ValueError: died = 9999
        if died > 1930: continue                                  # no dates for each song: keep composers who died by 1930
        full = names.get(parts[0], parts[0].replace("_", " "))
        comp = full.split()[-1] if surn[full.split()[-1]] == 1 else full
        comp = SURNAME.get(full, comp)
        nice = lambda x: re.sub(r"\b(No|Op|D|Nr)\.(?=\d)", r"\1. ", re.sub(r"\s+", " ", x.replace("_", " ")).strip())
        by, lic = f"OpenScore {label} (github.com/OpenScore/{folder})", "CC0"
        sid = sid_of(prefix, src)
        sm = smeta.get("/".join(parts[:-1]), {})
        extra = {"words": sm.get("lyricist", ""), "language": LANG.get(sm.get("language", ""), "")}
        if folder == "StringQuartets":
            add_ms(sid, src, comp, f"{comp} – {nice(parts[1])}", None, None, "", "", lic, by, 0, GENRE[folder]); continue
        set_dir, song = parts[1], re.sub(r"^\d+_", "", parts[2])
        m = re.match(r"^(\d+)_", parts[2]); order = int(m.group(1)) if m else 0
        if set_dir == "_": add_ms(sid, src, comp, f"{comp} – {nice(song)}", None, None, "", "", lic, by, 0, GENRE[folder])
        else: add_ms(sid, src, comp, f"{comp} – {nice(song)}", f"{comp} – {nice(set_dir)}", f"{fold(comp)}|{fold(set_dir)}", "", "", lic, by, order, GENRE[folder])
        pending[-1][2].update({k: v for k, v in extra.items() if v})
openscore("Lieder", "lied", "Lieder Corpus")
openscore("StringQuartets", "sq", "String Quartets")

# same song in two collections (Liederkreis, Op. 39 is in both): keep the first
seen_names = {fold(i["piece"]) + "|" + fold(i.get("setName") or "") for i in items}
uniq = []
for sid, src, it in pending:
    k = fold(it["piece"]) + "|" + fold(it.get("setName") or "") + "|" + it.get("movement", "")
    if k in seen_names: continue
    seen_names.add(k); uniq.append((sid, src, it))
pending = uniq

# convert with MuseScore (cached between runs), then strip what would give the answer away
CACHE = os.environ.get("SCORE_CACHE", ".score-cache")
os.makedirs(CACHE, exist_ok=True)
todo = [{"in": os.path.abspath(src), "out": os.path.abspath(os.path.join(CACHE, sid + ".mxl"))} for sid, src, it in pending if not os.path.exists(os.path.join(CACHE, sid + ".mxl"))]
if todo and os.environ.get("MSCORE"):
    for i in range(0, len(todo), 150):
        job = os.path.abspath(os.path.join(CACHE, "job.json")); json.dump(todo[i:i + 150], open(job, "w"))
        subprocess.run(shlex.split(os.environ["MSCORE"]) + ["-j", job], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3600)
        print("converted", min(i + 150, len(todo)), "/", len(todo), flush=True)
STRIP = [re.compile(p, re.S) for p in (r"<credit(?=[\s>]).*?</credit>", r"<work>.*?</work>", r"<movement-title>.*?</movement-title>",
                                         r"<movement-number>.*?</movement-number>", r"<creator(?=[\s>])[^>]*>.*?</creator>", r"<part-abbreviation>.*?</part-abbreviation>", r"<words(?=[\s>])[^>]*>[^<]*(?:Lied|Song|Op\.|No\.)[^<]*</words>")]
kept = 0
for sid, src, it in pending:
    cached = os.path.join(CACHE, sid + ".mxl")
    if not os.path.exists(cached): continue
    try:
        z = zipfile.ZipFile(cached)
        root = re.search(r'full-path="([^"]+)"', z.read("META-INF/container.xml").decode()).group(1)
        xml = z.read(root).decode("utf-8")
    except Exception as e:
        print("skip", sid, e); continue
    for p in STRIP: xml = p.sub("", xml)
    xml = re.sub(r"<part-name>.*?</part-name>", '<part-name print-object="no"></part-name>', xml, flags=re.S)        # required elements: empty, not removed
    xml = re.sub(r"<instrument-name>.*?</instrument-name>", "<instrument-name></instrument-name>", xml, flags=re.S)
    xml = xml.replace("<rights>", f"<rights>{it['license']}. {it['by']}. ").replace("</identification>", "</identification>") if "<rights>" in xml else xml.replace("<identification>", f"<identification><rights>{it['license']}. {it['by']}</rights>", 1)
    it["measures"] = len(re.findall(r"<measure\b", xml.split("</part>")[0]))
    if it["measures"] < 4: continue
    with zipfile.ZipFile(os.path.join(OUT, sid + ".mxl"), "w", zipfile.ZIP_DEFLATED) as w:
        w.writestr("META-INF/container.xml", f'<?xml version="1.0" encoding="UTF-8"?><container><rootfiles><rootfile full-path="score.xml"/></rootfiles></container>')
        w.writestr("score.xml", xml)
    items.append(it); kept += 1
print(kept, "MusicXML scores of", len(pending))

for it in items: it["answerKey"] = re.sub(r"[^a-z0-9]+", "-", it["piece"].lower()).strip("-")
sets = collections.defaultdict(list)
for it in items:
    if it["set"]: sets[it["set"]].append([it["piece"], it["answerKey"], it.get("order") or (int(re.search(r"(\d+)$", it["piece"]).group(1)) if re.search(r"(\d+)$", it["piece"]) else 0)])
for it in items: it.pop("order", None)
# a "set" with one piece is just a piece
for k, v in list(sets.items()):
    if len({x[1] for x in v}) < 2:
        for it in items:
            if it["set"] == k: it["set"] = it["setName"] = None
        del sets[k]
out = {"pieces": items, "sets": {k: {"name": next(i["setName"] for i in items if i["set"] == k), "members": [x[:2] for x in sorted({x[1]: x for x in v}.values(), key=lambda x: x[2])]} for k, v in sets.items()}}
json.dump(out, open("data/scores.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(items), "scores;", len({i["piece"] for i in items}), "distinct answers;", len(sets), "sets;", len({i["composer"] for i in items}), "composers")
print(collections.Counter(i["composer"] for i in items).most_common(40))
