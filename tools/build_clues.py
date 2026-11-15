"""Turn the downloaded facts into quiz-bowl style clues: specific and obscure first, more obvious later.

Reads data/catalog.json, sources/clue-facts.json (Wikidata, CC0), sources/clue-search.json, sources/wikidata-people.json,
sources/wikidata-works.json. Writes data/clues.json:
  people[name]       clues about a performer   ("{Who} studied with Theodor Leschetizky")
  composers[name]    clues about a composer    ("{Composer} was buried at Père Lachaise Cemetery")
  works[pieceKey]    clues about the piece     ("{It} was first performed at La Scala")
  years[year]        things that happened the year a recording was made
Each clue has a level from 1 (obscure) to 3 (fairly well known); the game adds the plainer clues after these.
{Who}, {Composer} and {It} are filled in by the game ("This tenor", "The composer", "This opera").
Run: python3 tools/build_clues.py
"""
import json, re, unicodedata, collections

def load(p, d=None):
    try: return json.load(open(p, encoding="utf-8"))
    except FileNotFoundError: return {} if d is None else d
def fold(s): return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()
def toks(s): return {w for w in re.findall(r"[a-z]+", fold(s)) if len(w) > 2}

cat = load("data/catalog.json")
facts, found = load("sources/clue-facts.json"), load("sources/clue-search.json")
people, works = load("sources/wikidata-people.json"), load("sources/wikidata-works.json")

def trusted(name, label):
    a, b = toks(name), toks(label or "")
    return bool(a) and bool(b) and (a == b or (min(len(a), len(b)) >= 2 and (a <= b or b <= a)) or (a & b and len(a) == 1))
def year(v):
    m = re.match(r"^(\d{4})-", v or "")
    return int(m.group(1)) if m else None
def listing(vals, n=2):
    vals = [v for v in vals if v][:n]
    return " and ".join(vals) if len(vals) <= 2 else ", ".join(vals[:-1]) + " and " + vals[-1]
def clean_vals(vals, banned):
    """drop values that would give the answer away (they contain a word of the answer's name) or are unreadable"""
    out = []
    for v in vals or []:
        if re.match(r"^(Q\d+|t\d+|http)", v) or len(v) > 80: continue
        if toks(v) & banned: continue
        out.append(v)
    return out

def person_clues(qid, banned, subj):
    f = facts.get(qid) or {}
    c = []
    def add(lvl, text): c.append({"t": text, "lvl": lvl})
    v = clean_vals(f.get("P119"), banned)
    if v: add(1, f"{subj} is buried " + ("at " if re.search(r"(?i)cemetery|friedhof|cimitero|cimetière|church|abbey|cathedral|basilica|chapel|kirche|mausoleum|pantheon|panthéon|crypt|tomb", v[0]) else "in ") + v[0])
    v = clean_vals(f.get("P166"), banned)
    if v: add(1, f"{subj} received the {v[0]}")
    v = clean_vals(f.get("P26"), banned)
    if v: add(1, f"{subj} was married to {listing(v)}")
    v = clean_vals(f.get("P802"), banned)
    if v: add(1, f"{subj} taught {listing(v)}")
    v = clean_vals(f.get("P20"), banned)
    if v: add(1, f"{subj} died in {v[0]}")
    for p, rel in (("P22", "father"), ("P25", "mother")):
        v = clean_vals(f.get(p), banned)
        if v: add(1, f"{subj}'s {rel} was {v[0]}")
    v = clean_vals(f.get("P1066"), banned)
    if v: add(2, f"{subj} studied with {listing(v)}")
    v = clean_vals(f.get("P69"), banned)
    if v: add(2, f"{subj} studied at the {v[0]}" if not v[0].lower().startswith("the ") else f"{subj} studied at {v[0]}")
    the = lambda x: x if re.match(r"(?i)the ", x) else "the " + x
    v = [x for x in clean_vals(f.get("P108"), banned) if not re.search(r"(?i)welte|victor|columbia|edison|aeolian|ampico|duo-art", x)]
    if v: add(2, f"{subj} worked at {the(v[0])}" if re.search(r"(?i)universit|conservat|hochschule|academ|school|college|institut|opera|theat|orchest", v[0]) else f"{subj} worked for {v[0]}")
    v = clean_vals(f.get("P463"), banned)
    if v: add(2, f"{subj} was a member of {the(v[0])}")
    v = [x for x in clean_vals(f.get("P800"), banned) if not re.match(r"(?i)(symphony|piano sonata|sonata|string quartet|piano concerto|concerto|piano trio|mass|requiem)\b", x)]
    if v: add(2, f"{subj} is known for {listing(v)}")
    v = clean_vals(f.get("P19"), banned)
    if v: add(3, f"{subj} was born in {v[0]}")
    return c

def work_clues(qid, banned, composer_banned):
    f = facts.get(qid) or {}
    c = []
    def add(lvl, text, names_composer=False): c.append({"t": text, "lvl": lvl, **({"composer": True} if names_composer else {})})
    v = clean_vals(f.get("P825"), banned)
    if v: add(1, f"{{It}} is dedicated to {listing(v)}")
    v = clean_vals(f.get("P674"), banned)
    if len(v) >= 2: add(1, f"Its characters include {listing(v)}")
    v = clean_vals(f.get("P87"), banned) + clean_vals(f.get("P676"), banned)
    if v: add(1, f"{{It}} has words by {listing(v)}")
    v = clean_vals(f.get("P144"), banned) + clean_vals(f.get("P1877"), banned)
    if v: add(2, f"{{It}} is based on {listing(v, 1)}")
    v = clean_vals(f.get("P840"), banned)
    if v: add(2, f"{{It}} is set in {listing(v)}")
    place = clean_vals(f.get("P4647"), banned)
    when = year((f.get("P1191") or [""])[0])
    if place and when: add(2, f"{{It}} was first performed in {when}, at {place[0]}")
    elif place: add(2, f"{{It}} was first performed at {place[0]}")
    elif when: add(2, f"{{It}} was first performed in {when}")
    w = year((f.get("P571") or [""])[0])
    if w and w != when: add(2, f"{{It}} was written in {w}")
    v = clean_vals(f.get("P407"), banned)
    if v and v[0] != "English": add(3, f"{{It}} is in {v[0]}")
    return c

# a few events for each year, for year clues (stable facts; checked by hand)
YEARS = {
    1900: ["Puccini's Tosca had its premiere in Rome", "the Exposition Universelle opened in Paris"],
    1901: ["Queen Victoria died", "Rachmaninoff's Second Piano Concerto had its first complete performance", "the first Nobel Prizes were awarded"],
    1902: ["Debussy's Pelléas et Mélisande had its premiere in Paris", "Enrico Caruso made his first recordings, in Milan"],
    1903: ["the Wright brothers made their first powered flight"],
    1904: ["Puccini's Madama Butterfly had its premiere at La Scala", "the New York City Subway opened"],
    1905: ["Richard Strauss's Salome had its premiere in Dresden", "Debussy's La mer had its premiere", "Einstein published his paper on special relativity"],
    1906: ["the San Francisco earthquake struck while Caruso was in the city", "Victor introduced the Victrola"],
    1907: ["Gustav Mahler left the Vienna Court Opera", "Picasso painted Les Demoiselles d'Avignon"],
    1908: ["Gustav Mahler made his debut at the Metropolitan Opera", "Ford introduced the Model T"],
    1909: ["Rachmaninoff's Third Piano Concerto had its premiere in New York", "Richard Strauss's Elektra had its premiere"],
    1910: ["Puccini's La fanciulla del West had its premiere at the Metropolitan Opera", "Stravinsky's The Firebird had its premiere in Paris"],
    1911: ["Gustav Mahler died", "Richard Strauss's Der Rosenkavalier had its premiere", "Stravinsky's Petrushka had its premiere"],
    1912: ["the Titanic sank", "Schoenberg's Pierrot lunaire had its premiere"],
    1913: ["Stravinsky's The Rite of Spring had its riotous premiere in Paris"],
    1914: ["the First World War began"],
    1915: ["the Lusitania was sunk"],
    1916: ["Enrique Granados died when the Sussex was torpedoed", "the Battle of the Somme was fought"],
    1917: ["the United States entered the First World War", "the first jazz record was made, by the Original Dixieland Jass Band"],
    1918: ["the First World War ended", "Claude Debussy died", "Puccini's Il trittico had its premiere at the Metropolitan Opera"],
    1919: ["the Treaty of Versailles was signed"],
    1920: ["women in the United States won the right to vote", "regular commercial radio broadcasting began"],
    1921: ["Enrico Caruso died"],
    1922: ["the BBC was founded", "Tutankhamun's tomb was found"],
    1923: ["the Charleston dance craze began with the song of the same name"],
    1924: ["Gershwin's Rhapsody in Blue had its premiere", "Giacomo Puccini died"],
    1925: ["Victor and Columbia began making records with microphones (electrical recording)", "Berg's Wozzeck had its premiere in Berlin"],
}

out = {"people": {}, "composers": {}, "works": {}, "years": {str(y): v for y, v in YEARS.items()}}
for r in cat["recordings"]:
    for p in r["performers"]:
        if p in out["people"]: continue
        v = people.get(p)
        if not v or not v.get("qid") or not trusted(p, v.get("label")): continue
        c = person_clues(v["qid"], toks(p) | toks(v.get("label")), "{Who}")
        if c: out["people"][p] = c
    comp = r["composer"]
    if comp not in out["composers"]:
        v = works.get(comp)
        if v and v.get("qid") and trusted(comp, v.get("label")):
            c = person_clues(v["qid"], toks(comp) | toks(v.get("label")), "{Composer}")
            if c: out["composers"][comp] = c
    k = r["pieceKey"]
    if k in out["works"]: continue
    q = r.get("workQid")
    hit = found.get(k)
    if not q and hit and hit.get("qid"):      # a Wikipedia search hit counts only if it's a work whose title matches ours
        hf = facts.get(hit["qid"]) or {}
        tw = toks(r["piece"].split(" – ", 1)[-1]) - toks(comp)
        if "human" not in (hf.get("P31") or []) and tw and len(tw & toks(hit["title"])) * 2 >= len(tw): q = hit["qid"]
    if not q: continue
    title = r["piece"].split(" – ", 1)[-1]
    banned = toks(title) | toks((facts.get(q) or {}).get("_label")) | toks(comp)
    c = work_clues(q, banned, toks(comp))
    if c: out["works"][k] = c
json.dump(out, open("data/clues.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(len(out["people"]), "performers,", len(out["composers"]), "composers,", len(out["works"]), "pieces with clues;",
      sum(len(v) for v in out["people"].values()) + sum(len(v) for v in out["composers"].values()) + sum(len(v) for v in out["works"].values()), "clues")
