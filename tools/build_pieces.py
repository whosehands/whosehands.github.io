"""Give every recording a clean piece name and build the full list of answer options.

Reads data/catalog.json and sources/wikidata-works.json; rewrites data/catalog.json with:
  recording.piece      clean display name of the whole work ("Chopin – Piano Sonata No. 2, Op. 35")
  recording.pieceKey   identity used to check answers (two names of the same work share a key)
  recording.movement   the part that plays, when the work has several parts (else "")
  catalog.pieceOptions [[name, key], ...] every work by every composer in the game
Run: python3 tools/build_pieces.py
"""
import json, re, unicodedata, collections

CAT = "data/catalog.json"
cat = json.load(open(CAT, encoding="utf-8"))
wd = json.load(open("sources/wikidata-works.json", encoding="utf-8"))

def fold(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower().replace("♭", " flat").replace("♯", " sharp")

STOP = set("the a an and of in for de du des la le les et en for to on op opus no nr no. op. in major minor dur moll flat sharp piano pianoforte works work set from aus".split())
TEMPO = r"(allegro|andante|adagio|grave|largo|presto|scherzo|finale|marche|march|rondo|menuet|menuetto|minuet|vivace|moderato|lento|allegretto|andantino|larghetto|intermezzo|romance|romanza|polacca|tempo|maestoso|prestissimo|molto|assai|introduction|introduzione|variations?|theme|thème|cavatina|aria|duet|quartet|chorus|act|scene|ouverture|overture|prelude|vorspiel|walzer|waltz|fantasie|fantaisie|fantasia|paraphrase|selection|selections|potpourri|part|teil)\b"
MULTI = r"(sonat|concert|konzert|symph|sinfon|suite|opera|oper\b|operetta|ballet|quartet|trio|quintet|serenade|partita|mass|messe|requiem|oratorio|cantata|carnaval|carneval|kreisleriana|kinderszenen|peer gynt|nutcracker|nussknacker)"

def numbers(s):
    """Opus / catalog number and item number, e.g. ('op', '27', '2')."""
    f = fold(s)
    m = re.search(r"\bop(?:us)?\.?\s*(?:posth\.?\s*)?\[?(\d+)\]?(?:[,.\s]*(?:no|nr|n°|num)\.?\s*(\d+))?", f)
    if m: return ("op", m.group(1), m.group(2) or "")
    m = re.search(r"\b(bwv|hwv|kv|k|d|s|hob\.?\s*[ivx]+|trv|woo|l|r)\.?\s*(\d+[a-z]?)(?:\s*/\s*(\d+)|[,.\s]*(?:no|nr)\.?\s*(\d+))?\b", f)
    if m: return (re.sub(r"\W", "", m.group(1)).replace("kv", "k"), m.group(2), m.group(3) or m.group(4) or "")
    return None

def keytok(s):
    return re.sub(r"\b([a-g])(?:[\s-]*(flat|sharp))?[\s-]+(major|minor|dur|moll)\b", lambda m: f" key{m.group(1)}{m.group(2) or ''}{'min' if m.group(3) in ('minor', 'moll') else 'maj'} ", s)
import difflib
def close(a, b):
    if a == b: return True
    if a.isdigit() or b.isdigit() or a.startswith("key") or b.startswith("key"): return False
    return len(a) > 3 and len(b) > 3 and difflib.SequenceMatcher(None, a, b).ratio() >= 0.8
def sim(tw, ow):
    if not tw or not ow: return 0.0
    k1, k2 = {w for w in tw if w.startswith("key")}, {w for w in ow if w.startswith("key")}
    if k1 and k2 and k1 != k2: return 0.0
    m = sum(1 for a in tw if any(close(a, b) for b in ow))
    return m / max(len(tw), len(ow))
def stem(w): return w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w
def title_words(s, surname):
    words = [stem(w) for w in re.findall(r"[a-z0-9]+", keytok(fold(s)))]
    return frozenset(w for w in words if w not in STOP and w != fold(surname) and len(w) > 1 and not w.isdigit()) | frozenset(w for w in words if w.isdigit())

def key_for(comp, s, surname):
    n = numbers(s)
    if n: return f"{fold(surname)}|{n[0]}{n[1]}|{n[2]}"
    return f"{fold(surname)}|t|" + " ".join(sorted(title_words(s, surname)))

ABBR = re.compile(r"(?:^|[\s,(])(no|nr|op|vol|st|ser|posth|ed|bwv|hob|[a-z])$", re.I)
INSTR = {"violin", "cello", "violoncello", "flute", "horn", "clarinet", "oboe", "organ", "harp", "guitar", "voice", "choir", "orchestra", "string", "strings", "trio", "quartet", "quintet"}
def split_movement(uniform):
    """'Sonatas, no. 2, op. 35, B♭ minor. Grave, Doppio movimento' -> (base, movement)."""
    u = (uniform or "").strip().rstrip(";").strip()
    if not u: return "", ""
    for m in re.finditer(r"\.\s+", u):
        head, tail = u[:m.start()], u[m.end():]
        if ABBR.search(head) or re.match(r"(no|nr|op)\b", tail, re.I): continue
        if re.search(MULTI, fold(head)) or re.match(TEMPO, fold(tail)):
            return head.strip(), tail.strip()
    m = re.match(r"^(.*?(?:major|minor|dur|moll))\s+(\S.*)$", u, re.I)
    if m and re.search(MULTI, fold(m.group(1))): return m.group(1).strip(), m.group(2).strip()
    return u, ""

def pretty_uniform(base):
    b = base
    b = re.sub(r"^Sonatas,\s*no\.\s*(\d+),\s*", r"Sonata No. \1, ", b)
    b = re.sub(r"^Concertos,\s*(?:piano,\s*orchestra,\s*)?no\.\s*(\d+),\s*", r"Piano Concerto No. \1, ", b)
    b = re.sub(r"^Concertos,\s*piano,\s*orchestra,\s*", "Piano Concerto, ", b)
    b = re.sub(r"^Symphonies,\s*no\.\s*(\d+),\s*", r"Symphony No. \1, ", b)
    b = re.sub(r"^(Nocturnes|Études|Etudes|Preludes|Préludes|Mazurkas|Waltzes|Polonaises|Impromptus|Ballades|Scherzos|Songs without words|Lieder ohne Worte),\s*(?:piano,\s*)?(op\.\s*\d+)\.?\s*No\.?\s*(\d+)",
               lambda m: {"Nocturnes": "Nocturne", "Études": "Étude", "Etudes": "Étude", "Preludes": "Prelude", "Préludes": "Prélude", "Mazurkas": "Mazurka",
                          "Waltzes": "Waltz", "Polonaises": "Polonaise", "Impromptus": "Impromptu", "Ballades": "Ballade", "Scherzos": "Scherzo",
                          "Songs without words": "Song Without Words", "Lieder ohne Worte": "Lied ohne Worte"}[m.group(1)] + f", {m.group(2).capitalize()} No. {m.group(3)}", b)
    b = re.sub(r"^(Ballades|Scherzos|Impromptus),\s*(?:piano,\s*)?no\.\s*(\d+),", lambda m: {"Ballades": "Ballade", "Scherzos": "Scherzo", "Impromptus": "Impromptu"}[m.group(1)] + f" No. {m.group(2)},", b)
    b = re.sub(r"^(Mazurkas|Waltzes|Polonaises|Nocturnes|Études|Etudes|Impromptus|Ballades|Scherzos|Preludes|Valses),\s*no\.\s*(\d+),\s*",
               lambda m: {"Mazurkas": "Mazurka", "Waltzes": "Waltz", "Polonaises": "Polonaise", "Nocturnes": "Nocturne", "Études": "Étude", "Etudes": "Étude",
                          "Impromptus": "Impromptu", "Ballades": "Ballade", "Scherzos": "Scherzo", "Preludes": "Prelude", "Valses": "Valse"}[m.group(1)] + f" No. {m.group(2)}, ", b)
    b = re.sub(r"^Rhapsodies hongroises\.\s*No\.?\s*(\d+)", r"Hungarian Rhapsody No. \1", b)
    b = re.sub(r"\bop\.", "Op.", b); b = re.sub(r",\s*,", ",", b)
    return b.strip(" ,.;")

GOOD_FORM = re.compile(r"music|composition|opera|ballet|song|hymn|nocturne|suite|concert|sonat|symph|étude|etude|waltz|mazurka|prelude|impromptu|scherzo|character piece|variation|lied|march|dance|operetta|anthem|fantas|rhapsod|instrumental|programme")
BAD_FORM = re.compile(r"film|television|video|album|single|series|production|literary|audio track|disambiguation|list|manuscript|printed|version|arrangement|translat|derivative|excerpt|lost|fragment|performance|radio|episode|program\b|choreograph|abandon|project|world premiere|edition")
SET_PARENT = re.compile(r"^(nocturnes|études|etudes|preludes|préludes|mazurkas|waltzes|valses|polonaises|impromptus|ballades|scherzi|scherzos|songs|lieder|pieśni|chants|rhapsodies|hungarian rhapsodies|rondos|chamber music|piano pieces|morceaux|pièces|humoresques|consolations|années|harmonies|transcendental|grandes études|lyric pieces|album|bagatelles|moments musicaux|op\.|six|twelve|24|12|6)", re.I)

surname_of = {}
for r in cat["recordings"]:
    if r["composer"] and r["composer"] != "Traditional":
        surname_of[r["composer"]] = (r.get("work") or r["piece"]).split(" – ")[0]

# 1. answer options from Wikidata (data/label-fixes.json corrects typos in Wikidata titles)
try: LABEL_FIX = json.load(open("data/label-fixes.json", encoding="utf-8"))
except FileNotFoundError: LABEL_FIX = {}
options = {}            # key -> display name
plain_of = {}           # key -> label without added catalog number
names_of = {}           # key -> the work's titles in several languages
key_of_item = {}        # wikidata id -> option key
kind_of_key = {}        # option key -> forms and genres text, for the genre filter
children_items = []     # (composer surname, label of an aria/movement, wikidata id of its parent work)
parents_of_key = collections.defaultdict(set)
work_by_key = {}
for comp, info in wd.items():
    if not info or comp not in surname_of: continue
    sn = surname_of[comp]
    works = {w["id"]: w for w in info["works"]}
    for w in works.values():
        forms = " ".join(w["forms"]).lower()
        if not w["label"] or re.match(r"^Q\d+$", w["label"]): continue
        if BAD_FORM.search(forms) or not GOOD_FORM.search(forms + " " + " ".join(w["genres"]).lower() + " " + w["label"].lower()): continue
        if "group of" in forms or "collection" in forms or "series" in forms:
            key_of_item.setdefault(w["id"], key_for(comp, w["label"], sn)); continue
        parents = [works[p] for p in w["partOf"] if p in works]
        if ("movement" in forms or "act" == forms.strip() or
                (parents and not any(SET_PARENT.search(p["label"]) or "group" in " ".join(p["forms"]).lower() for p in parents))):
            for p in parents:                          # a movement or aria of a bigger work: the bigger work is the answer
                children_items.append((sn, w["label"], p["id"]))
            continue
        label = re.sub(r"\s*\((?:%s|[^)]*%s[^)]*)\)" % (re.escape(sn), re.escape(sn)), "", LABEL_FIX.get(w["label"], w["label"])).strip()
        label = re.sub(r"\bnr\.?\s*", "No. ", label, flags=re.I); label = re.sub(r"\bop\.\s*", "Op. ", label, flags=re.I)
        plain = label
        if w["catalog"] and not numbers(label) and not re.search(r"\d", label):
            cats = [c for c in w["catalog"] if re.match(r"^(Op|S|BWV|K|D|TrV|WoO|Hob)", c)]
            if cats: label += f", {cats[0]}"
        name = f"{sn} – {label}"
        k = key_for(comp, label, sn)
        plain_of[k] = plain
        names_of[k] = [plain] + [a for a in w.get("alt", []) if a and len(a) < 120]
        kind_of_key[k] = (forms + " " + " ".join(w["genres"]).lower()).strip()
        key_of_item[w["id"]] = k
        parents_of_key[k] |= set(w["partOf"])
        if k not in options or (len(name) < len(options[k]) and numbers(name)): options[k] = name

# 1b. merge Wikidata entries that are the same work under two names (e.g. with and without a catalog number)
alias = {}
alt_names = {}          # other names of a work: still accepted when typed
groups = collections.defaultdict(list)
for k, n in options.items():
    sn, rest = n.split(" – ", 1)
    words = title_words(re.sub(r"\bn\.\s*(\d)", r"no \1", plain_of.get(k, rest)), sn)
    if words: groups[(sn, words)].append(k)
for ks in groups.values():
    if len(ks) < 2: continue
    keep = sorted(ks, key=lambda k: (0 if "|t|" not in k else 1, len(options[k])))[0]
    for k in ks:
        if k != keep: alias[k] = keep; alt_names[options[k]] = keep; options.pop(k, None)

# 2. clean the recordings' pieces and match them to options
unmatched = []
for r in cat["recordings"]:
    src = r.get("work") or r["piece"]
    sn = src.split(" – ")[0]
    raw = src.split(" – ", 1)[1] if " – " in src else src
    if "work" in r: base, mov = raw, r.get("part", "")
    else: base, mov = split_movement(raw)
    k = key_for(r["composer"], base, sn)
    k = alias.get(k, k)
    name = options.get(k)
    if not name and r.get("kind") == "record":
        tw = title_words(base, sn); best = None
        for csn, lab, pid in children_items:
            if csn != sn or pid not in key_of_item: continue
            ow = title_words(lab, sn)
            if not ow or not tw: continue
            j = sim(tw, ow)
            if j >= 0.75 and (best is None or j > best[0]): best = (j, pid)
        if best:
            pk = alias.get(key_of_item[best[1]], key_of_item[best[1]])
            if pk in options: k, name, mov = pk, options[pk], base
    if not name:
        # fall back to the closest option of the same composer by title words (numbers must agree)
        base_nonum = re.sub(r"\b(?:op|opus)\.?\s*(?:posth\.?\s*)?\[?\d+\]?(?:[,.\s]*(?:no|nr)\.?\s*\d+)?", " ", base, flags=re.I)
        tw = title_words(base_nonum, sn); best = None
        tdig = {w for w in tw if w.isdigit()}
        bnum = numbers(base)
        for ok, on in options.items():
            if not ok.startswith(fold(sn) + "|"): continue
            if bnum and "|t|" not in ok: continue           # numbered piece: only a same-number match (done above) or an unnumbered set
            j = 0
            for nm in names_of.get(ok, [plain_of.get(ok, on.split(" – ", 1)[1])]):
                ow = title_words(nm, sn)
                odig = {w for w in ow if w.isdigit()}
                if not tw or not ow or (tdig and odig and tdig != odig): continue
                if any(x in ow and x not in tw for x in INSTR): continue
                if tdig and not odig:   # a numbered piece inside an unnumbered set: only on a near-exact title match, and below any exact numbered match
                    t2 = {w for w in tw if not w.isdigit()}
                    if sim(t2, ow) >= 0.9 and sim(ow, t2) >= 0.9: j = max(j, 0.9 * sim(t2, ow))
                    continue
                j = max(j, sim(tw, ow))
            if j >= 0.6 and (best is None or j > best[0]): best = (j, ok, on)
        if best:
            k, name = best[1], best[2]
            dn = re.search(r"(?:,\s*|\bNo\.?\s*|\bNr\.?\s*)(\d+)\s*$", base)
            if dn and not re.search(r"\d", name.split(" – ", 1)[1]) and not mov: mov = "No. " + dn.group(1)
    if not name:
        name = f"{sn} – {base if 'work' in r else pretty_uniform(base)}"
        options.setdefault(k, name); unmatched.append(name); r["_unmatched"] = True
    r["piece"], r["pieceKey"], r["movement"] = name, k, mov
    r["_own"] = f"{sn} – {base}" if "work" in r and not (r.get("kind") == "record" and mov) else None

# the catalog's own clean name wins when it's the only name for that work
own = collections.defaultdict(set)
for r in cat["recordings"]: own[r["pieceKey"]].add(r["_own"])
for r in cat["recordings"]:
    names = own[r["pieceKey"]]
    wd_name = options.get(r["pieceKey"])
    own_better = r["_own"] and (not wd_name or r.get("_unmatched") or (numbers(r["_own"]) and not numbers(wd_name)))
    if len(names) == 1 and r["_own"] and not own_better:
        if wd_name and wd_name != r["_own"]:
            alt_names[r["_own"]] = r["pieceKey"]
            extra = re.search(r"(?:,\s*|\bNo\.?\s*|\bNr\.?\s*)(\d+)\s*$", r["_own"].split(" – ", 1)[1])
            if extra and not re.search(r"\d", wd_name.split(" – ", 1)[1]) and not r.get("movement"): r["movement"] = "No. " + extra.group(1)
        r["piece"] = wd_name
    elif len(names) == 1 and r["_own"]:
        old = options.get(r["pieceKey"])
        if old and old != r["_own"]: alt_names[old] = r["pieceKey"]
        r["piece"] = r["_own"]; options[r["pieceKey"]] = r["_own"]
    else: r["piece"] = options.get(r["pieceKey"], r["piece"])
    del r["_own"]; r.pop("_unmatched", None)

game_keys = {r["pieceKey"]: r for r in cat["recordings"]}
by_comp = collections.defaultdict(list)
for k, n in options.items(): by_comp[n.split(" – ")[0]].append(k)
dropped = 0
for gk, r in game_keys.items():
    gsn, gtitle = options.get(gk, r["piece"]).split(" – ", 1)
    gw = title_words(re.sub(r"\b(?:op|opus)\.?\s*\d+(?:[,.\s]*(?:no|nr)\.?\s*\d+)?", " ", gtitle, flags=re.I), gsn)
    gd = {w for w in gw if w.isdigit()}
    for ok in list(by_comp.get(gsn, [])):
        if ok == gk or ok in game_keys or ok not in options: continue
        on = options[ok].split(" – ", 1)[1]
        if numbers(on) and numbers(gtitle) and numbers(on) != numbers(gtitle): continue
        ow = title_words(re.sub(r"\b(?:op|opus)\.?\s*\d+(?:[,.\s]*(?:no|nr)\.?\s*\d+)?", " ", on, flags=re.I), gsn)
        od = {w for w in ow if w.isdigit()}
        if gd != od: continue
        if sim(gw, ow) >= 0.8 and sim(ow, gw) >= 0.8:
            alt_names[options.pop(ok)] = gk; alias[ok] = gk; dropped += 1
print(dropped, "duplicate names folded into works in the game")

# a set (e.g. "Three Intermezzi, Op. 117") next to its own numbered pieces ("Intermezzo, Op. 117 No. 2") reads as a duplicate:
# keep the set only when a recording plays it as a whole; its name still counts as an answer for any of its pieces
set_dropped = 0
numbered = collections.defaultdict(set)
for k in options:
    parts = k.split("|")
    if len(parts) == 3 and parts[1] != "t" and parts[2]: numbered[parts[0] + "|" + parts[1]].add(k)
for k in list(options):
    parts = k.split("|")
    if len(parts) == 3 and parts[1] != "t" and not parts[2] and numbered.get(parts[0] + "|" + parts[1]):
        set_name = options.pop(k); alt_names[set_name] = k; set_dropped += 1
        # list the set's other pieces too, so the one in the game isn't the only choice ("Three Intermezzi" -> Nos. 1-3)
        COUNT = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
        m = re.match(r"^\s*(\d{1,2}|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b", fold(set_name.split(" – ", 1)[1]))
        sample = next((options[c] for c in sorted(numbered[parts[0] + "|" + parts[1]]) if c in options), None)
        if m and sample and re.search(r"No\. \d+\s*$", sample):
            n = int(m.group(1)) if m.group(1).isdigit() else COUNT[m.group(1)]
            for i in range(1, min(n, 24) + 1):
                ck = f"{parts[0]}|{parts[1]}|{i}"
                if ck not in options: options[ck] = re.sub(r"No\. \d+\s*$", f"No. {i}", sample)
for r in cat["recordings"]:
    parts = r["pieceKey"].split("|")
    if len(parts) == 3 and parts[1] != "t" and parts[2]:
        r.setdefault("_setKey", parts[0] + "|" + parts[1] + "|")
    elif len(parts) == 3 and parts[1] != "t" and not parts[2] and r["pieceKey"] not in options:
        pre = parts[0] + "|" + parts[1] + "|"
        r["_setChildren"] = sorted(k for k in options if k.startswith(pre) and k != pre)   # a selection from a set: any piece of the set counts
print(set_dropped, "set names folded under their numbered pieces")

children = collections.defaultdict(set)
for k, ps in parents_of_key.items():
    for pid in ps:
        if pid in key_of_item: children[alias.get(key_of_item[pid], key_of_item[pid])].add(alias.get(k, k))
for r in cat["recordings"]:
    acc = set(children.get(r["pieceKey"], set())) | ({r.pop("_setKey")} if "_setKey" in r else set()) | set(r.pop("_setChildren", []))
    acc = sorted(acc - {r["pieceKey"]})
    if acc: r["acceptKeys"] = acc
    else: r.pop("acceptKeys", None)

# genre, for the practice filters
def genre_of(r):
    if r.get("genreHint"): return r["genreHint"]
    text = fold(r["piece"] + " " + (r.get("movement") or "") + " " + (r.get("rollLabel") or ""))
    kinds = kind_of_key.get(r["pieceKey"], "")
    cdesc = fold(((wd.get(r["composer"]) or {}).get("description")) or "")
    if re.search(r"\b(rag|fox-?trot|one-?step|two-?step|tango|revue|blues|cake-?walk|shimmy)\b", text):
        return "Popular & dance"
    if re.search(r"opera|operetta|ballet|dramatico|stage|musical theatre|singspiel|zarzuela", kinds) or re.search(
            r"\b(opera|operette|reminiscences|paraphrase de concert|fantasi[ae]? (?:on|sur|uber|über)|lohengrin|tannhauser|tristan|meistersinger|parsifal|rienzi|ring des|faust|carmen|aida|rigoletto|trovatore|traviata|boheme|tosca|madama butterfly|pagliacci|cavalleria|manon|werther|thais|lakme|samson|norma|don juan|don giovanni|lustige witwe|fledermaus|mikado|gondoliers|yeomen|henry viii|tiefland|guillaume tell|juive|hoffmann|frau luna|sadko|rose-marie|firefly)\b", text):
        return "Opera & stage"
    if re.search(r"symphon|concert|overture|orchestral|suite|tone poem", kinds) or re.search(r"\b(symphony|concerto|overture|ouverture|peer gynt|finlandia|heldenleben|suite)\b", text):
        return "Orchestral"
    if re.search(r"popular|ragtime|jazz|foxtrot|tango|dance music", kinds) or re.search(r"songwriter|popular|ragtime|bandleader|tin pan|cabaret|operetta|musical", cdesc):
        return "Popular & dance"
    if re.search(r"ohne worte|without words|melod|albumbl", text): return "Piano music"
    if re.search(r"\bsong|lied|hymn|aria|anthem", kinds) or re.search(r"\b(lied|lieder|song|songs|hymn|gesang|ständchen|standchen)\b", text):
        return "Songs"
    return "Piano music"
for r in cat["recordings"]:
    r["genre"] = genre_of(r)
    if r["genre"] == "Songs" and r.get("kind") != "record": r["genre"] = "Piano music"   # a pianist's song transcription is piano music
    if r["genre"] == "Songs": r["genre"] = "Art songs" if r.get("artSong") else "drop"
# the game keeps opera, art songs, orchestral and piano music; popular songs and instrumental solos are left out
VOCAL = {"soprano", "tenor", "baritone", "bass", "contralto", "mezzo-soprano", "vocalist", "chorus"}
for r in cat["recordings"]:   # an aria played by a studio cornet, flute or violin is an instrumental solo, not opera
    roles = set(r.get("roles") or [])
    if r.get("kind") == "record" and r["genre"] == "Opera & stage" and not roles & VOCAL and not roles & {"orchestra", "conductor"}: r["genre"] = "drop"
cat["recordings"] = [r for r in cat["recordings"] if r["genre"] in ("Opera & stage", "Art songs", "Orchestral", "Piano music")]
print(collections.Counter(r["genre"] for r in cat["recordings"]))

# one person under two names (e.g. "Eugenie Adam" and "Eugenie Adam-Benard"): Wikidata gives both the same id, so use one name
try: _people = json.load(open("sources/wikidata-people.json", encoding="utf-8"))
except FileNotFoundError: _people = {}
def _toks(n): return {w for w in re.findall(r"[a-z]+", fold(n)) if len(w) > 1}
def trusted(name, v):
    """Keep a Wikidata match only if it is the same name (one contains the other), never a generic class like 'orchestra'."""
    if not v or not v.get("label"): return False
    a, b = _toks(name), _toks(v["label"])
    return bool(a) and bool(b) and (a == b or (min(len(a), len(b)) >= 2 and (a <= b or b <= a)))
_people = {k: (v if trusted(k, v) else None) for k, v in _people.items()}
_by_qid = collections.defaultdict(collections.Counter)
for r in cat["recordings"]:
    for p in r["performers"]:
        q = (_people.get(p) or {}).get("qid")
        if q: _by_qid[q][p] += 1
_canon = {}
for q, names in _by_qid.items():
    if len(names) < 2: continue
    label = next((v.get("label") for v in _people.values() if v and v.get("qid") == q), None)
    keep = label if label in names else names.most_common(1)[0][0]
    for n in names: _canon[n] = keep
for r in cat["recordings"]:
    if any(p in _canon for p in r["performers"]):
        r["performers"] = [_canon.get(p, p) for p in r["performers"]]
        r["performerDates"] = {_canon.get(k, k): v for k, v in (r.get("performerDates") or {}).items()}
print(len(_canon), "performer names merged into", len(set(_canon.values())))

# how well known the composer and the performers are (number of Wikipedia articles), for the practice filters
people = _people   # only trusted matches
def tier(n, hi, mid): return "famous" if n >= hi else "known" if n >= mid else "obscure"
for r in cat["recordings"]:
    r["composerFame"] = tier(((wd.get(r["composer"]) or {}).get("sitelinks") or 0), 60, 20)
    best = max(((people.get(p) or {}).get("sitelinks") or 0) for p in r["performers"])
    r["performerFame"] = "famous" if r.get("famous") and best < 30 else tier(best, 30, 8)
print("composers:", collections.Counter(r["composerFame"] for r in cat["recordings"]), "performers:", collections.Counter(r["performerFame"] for r in cat["recordings"]))

# manual fixes from player reports: data/overrides.json maps a recording id to fields to replace
try: overrides = json.load(open("data/overrides.json", encoding="utf-8"))
except FileNotFoundError: overrides = {}
for r in cat["recordings"]:
    for k, v in (overrides.get(r["id"]) or {}).items(): r[k] = v
cat["recordings"] = [r for r in cat["recordings"] if not r.get("exclude")]

# drop option names that collide (same text, different key)
seen = collections.Counter(options.values())
cat["pieceOptions"] = sorted(([n, k] for k, n in options.items() if seen[n] == 1 or any(r["pieceKey"] == k for r in cat["recordings"])), key=lambda x: x[0])
cat.pop("extraPieces", None)
cat["pieceAliases"] = sorted([n, alias.get(k, k)] for n, k in alt_names.items() if n not in options.values())
shown = set(options.values()) | {n for n, _ in cat["pieceAliases"]}
missing = [r["piece"] for r in cat["recordings"] if r["piece"] not in shown]
cat["pieceAliases"] += sorted({(r["piece"], r["pieceKey"]) for r in cat["recordings"] if r["piece"] not in shown})
cat["pieceAliases"] = [list(x) for x in cat["pieceAliases"]]
print(len(missing), "answers accepted without being listed")
for r in cat["recordings"]:
    r["piece"] = r["piece"].replace("\u0361", ""); r["composer"] = r["composer"].replace("\u0361", "")
cat["pieceOptions"] = [[n.replace("\u0361", ""), k] for n, k in cat["pieceOptions"]]
json.dump(cat, open(CAT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(cat["pieceOptions"]), "answer options;", len(set(r["pieceKey"] for r in cat["recordings"])), "distinct pieces in the game;",
      len(unmatched), "recordings named from their own catalog entry")
