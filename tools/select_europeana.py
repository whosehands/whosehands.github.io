"""Turn Europeana's early recordings into records for the catalog (run before build_records.py).

Reads sources/europeana-audio.json (tools/fetch_europeana.py) and sources/europeana-media.json (the audio files that were
checked to play). Keeps classical music only: a known classical composer, no folk or popular songs, no band medleys.
Reads the people and the opera from each provider's own way of writing them:
  - Phonobase (Rhône-Alpes Laboratory for Historical Research, CC BY-NC-ND 4.0): "Faust ; scène de l'église",
    creators = composer and lyricist, contributors = performers ("Muratore, Lucien (1876-1954)").
  - National Library of Finland (public domain): creators marked "(säv.)" = composer, contributors
    "Ida Ekman (soprano). Karl Ekman (piano).", the opera in the description ("Aria from the opera Ernani").
Skips a recording that's already in the game from the Library of Congress or Wikimedia Commons, and repeated copies
of the same performance. Writes sources/europeana-selected.json in the same shape as sources/loc-selected.json.
"""
import json, re, hashlib, unicodedata, collections

def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except FileNotFoundError: return d
def fold(s): return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()
def words(s): return {w for w in re.findall(r"[a-z]+", fold(s)) if len(w) > 2}

items = load("sources/europeana-audio.json", [])
media = load("sources/europeana-media.json", {})
cat = load("data/catalog.json", {"recordings": []})["recordings"]
wd = load("sources/wikidata-works.json", {})
earlier = load("sources/loc-selected.json", []) + load("sources/commons-selected.json", [])

# composers: the catalog's own spelling of each name, plus classical composers the catalog doesn't have yet
names = collections.Counter(r["composer"] for r in cat if r.get("composer") and r["composer"] != "Traditional")
for r in earlier: names.update(r["composers"][:1])
EXTRA = """Benjamin Godard|Fromental Halévy|Ernest Reyer|Émile Paladilhe|André Messager|Édouard Lalo|Léo Delibes|Adolphe Adam|
Daniel Auber|François-Adrien Boieldieu|Ferdinand Hérold|Aimé Maillart|Cécile Chaminade|Reynaldo Hahn|Gabriel Fauré|Henri Duparc|
Ernest Chausson|Charles-Marie Widor|Augusta Holmès|César Franck|Vincent d'Indy|Alfred Bruneau|Gustave Charpentier|Xavier Leroux|
Christoph Willibald Gluck|Jean-Baptiste Lully|Jean-Philippe Rameau|André Grétry|Étienne Méhul|Victor Massé|Louis Clapisson|
Jean Sibelius|Oskar Merikanto|Fredrik Pacius|Erkki Melartin|Armas Järnefelt|Robert Kajanus|Selim Palmgren|Toivo Kuula|Leevi Madetoja|
Edvard Grieg|Christian Sinding|Halfdan Kjerulf|Wilhelm Peterson-Berger|Wilhelm Stenhammar|August Söderman|Emil Sjögren|
Giulio Caccini|Francesco Paolo Tosti|Luigi Denza|Hans Hermann|Adolf Jensen|Carl Loewe|Peter Cornelius|Jacques Offenbach|Camille Saint-Saëns|
Jules Massenet|Ambroise Thomas|Giacomo Meyerbeer|Léo Delibes|Georges Bizet|Charles Gounod|Ruggero Leoncavallo""".replace("\n", "").split("|")
for n in EXTRA: names.setdefault(n.strip(), 0)
by_surname = collections.defaultdict(list)
for n, c in names.most_common():
    by_surname[fold(re.split(r"\s+", n)[-1])].append(n)
POPULAR = re.compile(r"(?i)songwriter|popular|vaudeville|music hall|chansonnier|cabaret|ragtime|lyricist|bandleader|film")
def classical(n):
    v = wd.get(n)
    if n in EXTRA: return True
    if not v: return False
    d = (v.get("description") or "").lower()
    return "composer" in d and not POPULAR.search(d) and (v.get("sitelinks") or 0) >= 20
def composer_of(raw):
    """'Godard, Benjamin' / 'Pacius, Fredrik (säv.)' / 'Verdi, Giuseppe' -> the catalog's name, if a classical composer"""
    raw = re.sub(r"\s*[(<].*?[)>]", "", raw).strip()
    if "," in raw: last, first = [x.strip() for x in raw.split(",", 1)]
    else: parts = raw.split(); last, first = (parts[-1] if parts else ""), " ".join(parts[:-1])
    for n in by_surname.get(fold(last.split()[-1] if last.split() else last), []):
        given = re.split(r"\s+", n)[0]
        if first and fold(first)[:1] != fold(given)[:1]: continue
        if classical(n): return n
    return None

def person(raw):
    """'Muratore, Lucien (1876-1954)' -> 'Lucien Muratore'; 'Marty (Mme George Marty)' -> 'Marty'; 'Lucas, Mme' -> 'Mme Lucas'"""
    raw = re.sub(r"\s*\(.*?\)\s*", " ", raw).strip().strip(".")
    if "," in raw:
        last, first = [x.strip() for x in raw.split(",", 1)]
        raw = f"{first} {last}".strip()
    return re.sub(r"\s+", " ", raw)
ENSEMBLE = re.compile(r"(?i)garde r[ée]publicaine|republican guard|band|orchest|musique|fanfare|harmonie|choeur|chœur|chorus|quartet|quatuor|trio")

ROLE = {"sopraano": "soprano", "soprano": "soprano", "tenori": "tenor", "tenor": "tenor", "baritoni": "baritone", "baritone": "baritone",
        "basso": "bass", "bass": "bass", "altto": "contralto", "contralto": "contralto", "mezzosopraano": "mezzo-soprano", "mezzo-soprano": "mezzo-soprano",
        "laulu": "vocalist", "vocal": "vocalist", "piano": "piano", "viulu": "violin", "violin": "violin", "sello": "cello", "cello": "cello", "urut": "organ"}
def finnish_people(it):
    """'Ida Ekman (soprano). Karl Ekman (piano).' -> [['Ida Ekman', 'soprano'], ['Karl Ekman', 'piano']]"""
    text = (it["contributors"] or [""])[0]       # the library's own Finnish text comes first; later ones are machine translations
    out = []
    for name, role in re.findall(r"([A-ZÅÄÖÉ][\w'\-]+(?:[ \-][A-ZÅÄÖÉ][\w'\-]+)+)\s*\(([^)]*)\)", text):
        r = re.split(r"[:,\s]+", role.strip().lower())
        r = next((ROLE[x] for x in reversed(r) if x in ROLE), "vocalist")
        if not ENSEMBLE.search(name): out.append([name, r])
    return out

# opera names, so "Le Trouvère ; Dieu que ma voix implore" is filed under Il trovatore (Wikidata knows the French names too)
STAGE = {}
for comp, v in wd.items():
    for w in (v or {}).get("works", []):
        if re.search(r"dramatico|opera|operetta|stage", " ".join(w.get("forms", [])).lower()):
            for nm in [w["label"]] + w.get("alt", []): STAGE.setdefault((comp, fold(nm)), w["label"])
OPERA = {fold(k): v for k, v in {   # for composers Wikidata's list doesn't cover yet
    "La Juive": "La Juive", "Paillasse": "Pagliacci", "Jocelyn": "Jocelyn", "Le Trouvère": "Il trovatore", "Le Barbier de Séville": "The Barber of Seville",
    "Guillaume Tell": "Guillaume Tell", "Sigurd": "Sigurd", "Le Chalet": "Le chalet", "Si j'étais roi": "Si j'étais roi", "Le Postillon de Lonjumeau": "Le postillon de Lonjumeau",
    "La Dame blanche": "La dame blanche", "Les Dragons de Villars": "Les dragons de Villars", "Le Coeur et la main": "Le cœur et la main",
    "Les Cloches de Corneville": "Les cloches de Corneville", "Lakmé": "Lakmé", "Le Roi d'Ys": "Le roi d'Ys", "Les Noces de Jeannette": "Les noces de Jeannette",
    "Le Pré aux clercs": "Le pré aux clercs", "Zampa": "Zampa", "Fra Diavolo": "Fra Diavolo", "Le Domino noir": "Le domino noir", "Galathée": "Galathée",
    "Paul et Virginie": "Paul et Virginie", "La Favorite": "La favorite", "Lucie de Lammermoor": "Lucia di Lammermoor", "Les Pêcheurs de perles": "Les pêcheurs de perles",
    "Ernani": "Ernani", "Se fossi re": "Si j'étais roi", "La Vie de bohème": "La bohème", "La Vie de bohême": "La bohème", "La Bohème": "La bohème",
    "Orphée": "Orfeo ed Euridice", "Orphée et Eurydice": "Orfeo ed Euridice", "Hänsel et Gretel": "Hänsel und Gretel", "La Walkyrie": "Die Walküre",
    "François les bas bleus": "François les bas-bleus", "Le Vaisseau fantôme": "The Flying Dutchman", "Les Noces de Figaro": "The Marriage of Figaro",
    "La Flûte enchantée": "The Magic Flute", "Les Contes d'Hoffmann": "The Tales of Hoffmann", "Le Freischütz": "Der Freischütz", "Sicilianska vespern": "Les vêpres siciliennes", "Rigoletto": "Rigoletto", "La Traviata": "La traviata", "Aïda": "Aida"}.items()}
OPERA_COMPOSERS = set("Verdi Puccini Donizetti Rossini Bellini Gounod Bizet Meyerbeer Massenet Wagner Thomas Halévy Leoncavallo Mascagni Ponchielli Delibes Offenbach Adam Auber Boieldieu Hérold Maillart Reyer Lalo Messager Godard Giordano Cilea Mozart Weber Flotow".split())
SONG_COMPOSERS = set("Tosti Denza Chaminade Hahn Fauré Duparc Chausson Holmès Schubert Schumann Brahms Wolf Grieg Sibelius".split())
def opera_of(comp, name):
    f = fold(name.strip())
    return OPERA.get(f) or STAGE.get((comp, f))   # the list above wins: it names each opera the way the rest of the game does

SKIP = re.compile(r"(?i)fantaisie|fantasia|s[ée]lection|pot-?pourri|d[ée]fil[ée]|marche\b|march\b|polka|quadrille|kansanlaulu|kansansävelmä|folk ?(song|tune)|"
                  r"message|discours|speech|monologue|\bvårt land\b|\bmaamme\b|suomen laulu")
def year_of(it):
    m = re.match(r"\d{4}", str(it.get("year") or ""))
    return int(m.group()) if m else None

out, seen, why = [], set(), collections.Counter()
for it in items:
    url = media.get(it["id"])
    if not url: why["no playable audio"] += 1; continue
    y = year_of(it)
    if not y or y > 1925: why["no year"] += 1; continue
    text = " ".join([it["title"], it.get("description", ""), " ".join(it.get("subjects", []))])
    if SKIP.search(text): why["folk, band or spoken"] += 1; continue
    subj = fold("; ".join(x for x in it.get("subjects", []) if not x.startswith("http")))
    if re.search(r"popular music|folk music|spoken word|monologue|cafe-concert", subj): why["folk, band or spoken"] += 1; continue
    prov = it["provider"]
    if prov.startswith("National Library of Finland"):
        comps = [composer_of(c) for c in it["creators"] if "(säv.)" in c]
        people = finnish_people(it)
        opera = re.search(r"(?:from the opera|oopperasta|ur operan)\s+([^.;,]+)", it.get("description", ""), re.I)
        title, part = it["title"], ""
        place = (re.search(r"(?:Recorded|Äänitetty):\s*\[[^\],]*,\s*([^\]]+)\]", it.get("description", "")) or [None, ""])[1]
        where, lic, label = "National Library of Finland", "Public domain (National Library of Finland, via Europeana)", "Gramophone" if "Gramophone" in url else ("Victor" if "Victor" in url else "")
    else:
        comps = [composer_of(c) for c in it["creators"]]
        seen_p, people = set(), []
        for c in it["contributors"]:
            if c.startswith("http") or re.search(r"(?i)known as|\bdit\b|anonyme|ind[ée]termin|unknown|inconnu", c): continue
            if re.search(r"[\u0400-\u04ff]", c) and seen_p: continue     # the Cyrillic spelling of a name already given in Latin letters
            n = person(c)
            if not n or fold(n) in seen_p or fold(n) in {fold(x) for x in it["creators"] if x}: continue
            seen_p.add(fold(n)); people.append([n, "orchestra" if ENSEMBLE.search(n) else "vocalist"])
        # Europeana's machine translation of a name ("André Marshal" after "André Maréchal") isn't a second performer
        people = [p for i, p in enumerate(people) if not (len(p[0].split()) > 1 and any(q[0].split()[0] == p[0].split()[0] and len(q[0].split()) > 1 for q in people[:i]))]
        if len(people) > 1:   # the English copy of an ensemble's name ("Republican Guard") isn't a second performer
            people = [p for p in people if not (p[1] == "orchestra" and any(q[1] == "orchestra" and q is not p for q in people) and re.match(r"(?i)republican guard|the ", p[0]))]
        title, part, opera, place = it["title"], "", None, ""
        where, lic, label = "Phonobase (Rhône-Alpes Laboratory for Historical Research)", "CC BY-NC-ND 4.0 (Phonobase / LARHRA, via Europeana)", ""
    comps = [c for c in comps if c]
    if not comps: why["not a classical composer"] += 1; continue
    if not prov.startswith("National Library of Finland") and people:
        # Phonobase gives the instruments in its subject terms ("piano acc.", "violon solo", "piano à quatre mains")
        if re.search(r"(?i)it is said|some people claim|on dit que|certains pretendent|suppos", fold(it.get("description", ""))): people = people[:1]   # a guessed accompanist isn't credited
        if re.search(r"piano solo|piano a quatre mains|^piano$", subj): people = [[n, "piano"] for n, _ in people]
        else:
            solo = re.search(r"(violoncelle|violon|flute|cornet|piston|clarinette|mandoline|ocarina|accordeon)\s*(?:solo|,\s*piano acc|et piano acc)", subj)   # "cor anglais acc." is the accompaniment
            if solo: people[0][1] = {"violoncelle": "cello", "violon": "violin", "flute": "flute", "piston": "cornet", "clarinette": "clarinet", "mandoline": "mandolin", "accordeon": "accordion", "cor anglais": "english horn"}.get(solo.group(1), solo.group(1))
            acc = [{"violon": "violin", "violoncelle": "cello", "harpe": "harp", "orgue": "organ", "clarinette": "clarinet", "flute": "flute"}.get(a, a)
                   for a in re.findall(r"(piano|violoncelle|violon|flute|harpe|orgue|clarinette)\s*acc", subj)]
            if len(acc) >= 2 and len(people) == 1 + len(acc):                      # "violon acc, piano acc." with a singer and two players
                for q, a in zip(people[1:], acc): q[1] = a
            elif "piano acc" in subj and len(people) > 1 and (composer_of(people[-1][0]) or solo): people[-1][1] = "piano"   # Debussy accompanying Mary Garden
            elif acc and len(people) > 1 and not re.search(r"(?i)\b(duo|duet|duetto|trio|quatuor|quartet|scene|ensemble)\b", fold(title)):
                for q in people[1:]: q[1] = "performer"   # a second singer or the accompanist: Phonobase doesn't say which
    comp = comps[0]
    if not people: why["no performer named"] += 1; continue
    if all(r in ("orchestra",) for _, r in people) or all(r == "piano" for _, r in people) and prov.startswith("Rh"): why["band or unnamed"] += 1; continue
    # the opera: from the description (Finland), or the part before " ; " / ", " in the title (Phonobase)
    work = opera.group(1).strip() if opera else None
    if work: work = opera_of(comp, work) or work
    m = re.match(r"^(.+?)\s*[;:]\s*(.+)$", title) or re.match(r"^([^,]+),\s*(.+)$", title)
    if m and opera_of(comp, m.group(1)):
        work, part = opera_of(comp, m.group(1)), m.group(2).strip()
    elif m and not work and ";" in title and not prov.startswith("National Library of Finland") and comp.split()[-1] not in SONG_COMPOSERS:   # Phonobase writes "work ; part"
        work, part = m.group(1).strip(), m.group(2).strip()
    if work and not part: part = title
    part = re.sub(r"^\s*;\s*", "", part)
    roles = {r for _, r in people}
    if work: genre = "Opera & stage"
    elif roles & {"soprano", "tenor", "baritone", "bass", "contralto", "mezzo-soprano", "vocalist"}:
        genre = "Opera & stage" if comp.split()[-1] in OPERA_COMPOSERS and re.search(r"(?i)orkester|orchestra|orchestre", text) else "Art songs"
    elif roles <= {"piano"}: genre = "Piano music"
    else: genre = "Instrumental solos"
    # the same performance twice (Phonobase lists each copy of a cylinder)
    lead = people[0][0]
    dk = (fold(lead), fold(re.sub(r"\W+", " ", part or title)).strip())
    if dk in seen: why["another copy"] += 1; continue
    seen.add(dk)
    tw = words(part or title)
    same = [r for r in earlier if any(fold(lead).split()[-1:] == fold(n).split()[-1:] for n, _ in r["performers"]) and tw
            and len(tw & words(r["title"])) * 3 >= 2 * len(tw) and abs(r["year"] - y) <= 2]
    if same: why["already in the game"] += 1; continue
    rec = {
        "id": "eu-" + hashlib.md5(it["id"].encode()).hexdigest()[:10],
        "audio": url, "performers": people, "credits": [], "composers": [comp] + [c for c in comps[1:] if c != comp],
        "title": (part if work else title).strip().rstrip("."), "year": y, "yearMax": y, "date": str(y), "place": place,
        "label": label, "catalog": "", "format": f"{label} record" if label else "Cylinder or disc record",
        "source": re.sub(r"^http://", "https://", it.get("page") or it.get("europeana") or ""), "sourceName": where, "license": lic,
        "genres": ["Opera"] if genre == "Opera & stage" else ["Classical music"], "genreHint": "Songs" if genre == "Art songs" else genre,
        "artSong": genre == "Art songs",
    }
    if work: rec["opera"] = work
    out.append(rec)
json.dump(out, open("sources/europeana-selected.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(out), "Europeana recordings;", ", ".join(f"{v} {k}" for k, v in why.most_common()))
