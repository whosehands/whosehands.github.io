"""Build data/catalog.json for Whose Hands from Stanford's SUPRA roll metadata."""
import sys, re, json, os, shutil, random
src_json, supra_root, site = sys.argv[1], sys.argv[2], sys.argv[3]
rows = json.load(open(src_json, encoding='utf-8'))

def flip(name):
    name = (name or '').strip().rstrip(',').strip()
    if name.endswith('.') and len(name.split()[-1]) > 2: name = name[:-1]
    if ', ' in name:
        last, first = name.split(', ', 1)
        return (first + ' ' + last).replace("d' ", "d'").strip()
    return name

def clean_title(t):
    t = (t or '').strip()
    t = re.sub(r'\s*/\s*$', '', t)
    t = re.sub(r'\s*\((?:played by|nach)[^)]*\)', '', t, flags=re.I)
    t = t.split(' = ')[0]
    t = re.sub(r'\s+:\s*$', '', t)
    t = re.sub(r'\s{2,}', ' ', t).strip(' :;,').rstrip('.')
    return t[:1].upper() + t[1:]

SING = {"sonatas": "Sonata", "concertos": "Concerto", "symphonies": "Symphony", "preludes": "Prelude", "préludes": "Prélude", "nocturnes": "Nocturne",
        "études": "Étude", "etudes": "Étude", "waltzes": "Waltz", "valses": "Valse", "mazurkas": "Mazurka", "polonaises": "Polonaise", "ballades": "Ballade",
        "impromptus": "Impromptu", "scherzos": "Scherzo", "rhapsodies hongroises": "Hungarian Rhapsody", "rhapsodies": "Rhapsody", "intermezzi": "Intermezzo",
        "romances": "Romance", "fantasies": "Fantasy", "fantasien": "Fantasy", "marches militaires": "Marche militaire", "moments musicaux": "Moment musical",
        "songs without words": "Song Without Words", "lieder ohne worte": "Lied ohne Worte", "polkas": "Polka", "rondos": "Rondo", "variations": "Variations",
        "suites": "Suite", "quartets": "Quartet", "trios": "Trio", "overtures": "Overture", "hungarian dances": "Hungarian Dance", "ungarische tänze": "Hungarian Dance"}
def work_from_240(u):
    a = " ".join(v for c, v in u if c == "a").strip(" .,;:")
    m = " ".join(v for c, v in u if c == "m").strip(" .,;").lower()
    ns = [v.strip(" .,;") for c, v in u if c == "n"]
    r = " ".join(v for c, v in u if c == "r").strip(" .,;")
    p = " ".join(v for c, v in u if c == "p").strip(" .,;")
    k = " ".join(v for c, v in u if c == "k").strip(" .,;")
    arranged = any(c == "o" and "arr" in v for c, v in u)
    acts = [x for x in ns if re.search(r"(?i)aufzug|akt\b|act\b|atto\b|acte\b", x)]
    ns = [x for x in ns if x not in acts]
    if acts: p = (", ".join(acts) + (": " + p if p else "")).strip()
    if p.lower().startswith("suite") and not SING.get(a.lower()):
        sn_ = re.match(r"^\s*(?:no|nr)\.?\s*(\d+)", ", ".join(ns), re.I)
        return (a + " Suite" + (f" No. {sn_.group(1)}" if sn_ else "")).strip(), "", any(c == "o" and "arr" in v for c, v in u)
    nstr = ", ".join(ns)
    CATRE = r"(?:BWV|HWV|KV|K|D|S|WoO|TrV|Hob\.?\s*[IVX]+|L|R)\.?\s*\d+[a-z]?"
    num = re.match(r"^\s*(?:no|nr)\.?\s*(\d+)", nstr, re.I)
    opm = re.search(r"\b(op\.?\s*(?:posth\.?\s*)?\d+(?:\s*[,.]?\s*(?:no|nr)\.?\s*\d+)?)", nstr, re.I) or re.search(r"\b(" + CATRE + r")", nstr)
    sing = SING.get(a.lower())
    if sing:
        if sing in ("Sonata", "Concerto") and "piano" in m and "violin" not in m and "cello" not in m: sing = "Piano " + sing
        title = sing
        if num: title += f" No. {num.group(1)}"
        if r: title += f" in {r}"
        if opm:
            op = re.sub(r"(?i)\bop\.?\s*", "Op. ", opm.group(1)); op = re.sub(r"(?i)\s*[,.]?\s*\b(no|nr)\.?\s*", " No. ", op)
            title += f", {op}"
        if not num and not opm and nstr: title += f", {nstr}"
    else:
        title = a + (f", {nstr}" if nstr else "") + (f", {r}" if r else "")
        title = re.sub(r",\s*\(", " (", title)
        title = re.sub(r"(?i)\bop\.\s*", "Op. ", title)
    part = p or ("selections" if k.lower().startswith("selection") else "")
    return title.strip(" ,"), part, arranged

def years(r):
    rec = (r.get('recorded') or '')[:4]
    pub = r.get('pubyear') or ''
    pubyrs = [int(y) for y in re.findall(r'1[89]\d\d', pub)]
    if rec.isdigit():
        y = int(rec); return y, y, True, pubyrs
    if pubyrs:
        return min(pubyrs), max(pubyrs), len(pubyrs) == 1, pubyrs
    return None, None, False, pubyrs

FAMOUS = {"Ferruccio Busoni","Teresa Carreño","Eugen d'Albert","Wilhelm Backhaus","Ernő Dohnányi","Anna Nikolaevna Esipova","Arthur Friedheim",
  "Ossip Gabrilowitsch","Rudolph Ganz","Alfred Grünfeld","Mark Hambourg","Josef Hofmann","Raoul Koczalski","Frederic Lamond","Wanda Landowska",
  "Theodor Leschetizky","Josef Lhévinne","Guiomar Novaes","Vladimir de Pachmann","Ignace Jan Paderewski","Egon Petri","Raoul Pugno","Carl Reinecke",
  "Alfred Reisenauer","Camille Saint-Saëns","Olga Samaroff Stokowski","Emil von Sauer","Xaver Scharwenka","Ernest Schelling","Artur Schnabel",
  "Bernhard Stavenhagen","Fannie Bloomfield-Zeisler","Yolanda Mero","Felix Mottl","Arthur Nikisch","Isabelle Vengerova","James Reese Europe",
  "Leff Pouishnoff","Conrad Ansorge","Fanny Davies","Clotilde Kleeberg","Frieda Kwast-Hodapp","Rudolf Serkin","W. Sapellnikoff","Elly Ney"}

out, skipped = [], []
for r in rows:
    if not r.get('has_midi'): skipped.append((r['druid'], 'no midi')); continue
    y0, y1, exact, pubyrs = years(r)
    latest_pub = max(pubyrs) if pubyrs else None
    if latest_pub is None or latest_pub > 1925:
        skipped.append((r['druid'], 'published after 1925 or unknown')); continue
    performers = [flip(p['name']) for p in r.get('people', []) if re.search(r'instrumentalist|perform|pianist', p['role'])]
    if not performers: skipped.append((r['druid'], 'no performer')); continue
    composer = flip(r.get('composer'))
    if not composer:
        others = [flip(p['name']) for p in r.get('people', []) if not re.search(r'instrumentalist|perform|pianist|arranger', p['role'])]
        composer = others[0] if others else 'Traditional'
    cd = (r.get('composer_dates') or '').rstrip('.')
    title = clean_title(r.get('title245') or r.get('uniform') or '')
    uni = (r.get('uniform') or '').strip()
    uni = re.sub(r',\s*(piano|pianos?, \d hands)\s*,', ',', uni)
    uni = re.sub(r'\s*;\s*$', '', uni).replace(' ;', ';').strip(' ,.;:')
    work = uni if uni else title
    if r.get('u240'): wk, wpart, warr = work_from_240(r['u240'])
    else: wk, wpart, warr = title, '', False
    if not title: skipped.append((r['druid'], 'no title')); continue
    surname = composer.split()[-1] if composer != 'Traditional' else 'Traditional'
    perf_dates = {flip(p['name']): (p.get('dates') or '').rstrip('.') for p in r.get('people', [])}
    place = ''
    m = re.search(r'(Freiburg|Leipzig|New York|Paris|London)', (r.get('event_note','') + ' ' + json.dumps(r)), re.I)
    if m: place = m.group(1)
    out.append({
        'id': r['druid'],
        'performers': performers,
        'performerDates': {p: perf_dates.get(p, '') for p in performers},
        'composer': composer, 'composerDates': cd,
        'piece': f"{surname} – {work}",
        'work': f"{surname} – {wk}", 'part': wpart, 'arranged': warr,
        'rollLabel': title,
        'title': title,
        'yearMin': y0, 'yearMax': y1, 'yearExact': exact,
        'place': place, 'rollNumber': r.get('rollno',''),
        'format': 'Welte-Mignon piano roll',
        'midi': f"midi/{r['druid']}.mid",
        'source': f"https://purl.stanford.edu/{r['druid']}",
        'license': 'CC BY-NC-SA 4.0 (Stanford University Piano Roll Archive)',
        'famous': any(p in FAMOUS for p in performers),
    })
    os.makedirs(os.path.join(site, 'midi'), exist_ok=True)
    shutil.copyfile(os.path.join(supra_root, 'welte-red/midi-exp', r['druid'] + '_exp.mid'), os.path.join(site, 'midi', r['druid'] + '.mid'))

# Stable daily schedule: famous rolls twice as often early on, fixed seed so the order never changes.
rng = random.Random(1926)
fam = [x['id'] for x in out if x['famous']]; rest = [x['id'] for x in out if not x['famous']]
rng.shuffle(fam); rng.shuffle(rest)
order = []
while fam or rest:
    for _ in range(2):
        if fam: order.append(fam.pop())
    if rest: order.append(rest.pop())
# avoid the same pianist two days running where possible
by = {x['id']: x for x in out}
for i in range(1, len(order)):
    if by[order[i]]['performers'] == by[order[i-1]]['performers']:
        for j in range(i+1, len(order)):
            if by[order[j]]['performers'] != by[order[i-1]]['performers']:
                order[i], order[j] = order[j], order[i]; break

catalog = {'version': 1, 'epoch': '2026-11-08', 'schedule': order, 'recordings': out}
os.makedirs(os.path.join(site, 'data'), exist_ok=True)
json.dump(catalog, open(os.path.join(site, 'data/catalog.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(len(out), 'puzzles;', sum(x['famous'] for x in out), 'famous;', len(skipped), 'skipped')
from collections import Counter
print(Counter(s[1] for s in skipped))
print('exact years', sum(x['yearExact'] for x in out))
for x in [by[i] for i in order[:8]]: print(x['performers'], '|', x['piece'], '|', x['yearMin'], x['yearMax'])
