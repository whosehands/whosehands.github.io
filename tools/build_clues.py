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

MUSICAL = re.compile(r"(?i)music|musik|musique|musica|muzy|opera|oper\b|philharm|symphon|orchest|conservat|konservat|hochschule|academy of music|beaux-arts|prix de rome|grammy|choir|chor\b|quartet|kammersänger|singer|piano|violin|organ|composer|composition|concert|theat|scala|liceu|covent|bayreuth|juilliard|curtis|schola cantorum")
def aan(t): return ("an " if re.match(r"(?i)[aeiou]", t) else "a ") + t if t and not t.startswith("who ") else t
def person_clues(qid, banned, subj):
    """Only things that say something about the musician: teachers, pupils, music schools, posts, where they lived and worked."""
    f = facts.get(qid) or {}
    c = []
    def add(lvl, text): c.append({"t": text, "lvl": lvl})
    the = lambda x: x if re.match(r"(?i)the ", x) else "the " + x
    music = lambda vals: [x for x in vals if MUSICAL.search(x)]
    # relatives and partners, only those who mattered in music (see tools/fetch_clues.py for the rule)
    REL = {"P26": "{s} was married to {x}", "P451": "{s} had a relationship with {x}", "P22": "{s}'s father was {x}", "P25": "{s}'s mother was {x}",
           "P40": "{s} was the parent of {x}", "P3373": "{s}'s sibling was {x}", "P1038": "{s} was related to {x}"}
    for r in (f.get("_relatives") or [])[:6]:
        name, occ = r["name"], [o for o in r.get("occupations", []) if MUSICAL.search(o) or re.search(r"(?i)director|librettist|impresario|publisher|critic|dancer", o)]
        if r.get("marriedTo") and not occ: desc = "who married " + listing([m for m in r["marriedTo"] if not (toks(m) & banned)] or ["a composer"], 1)
        else: desc = listing(occ[:2], 2)
        if toks(name) & banned:                      # same surname as the answer (Clara Schumann): first name only
            first = [w for w in name.split() if not (toks(w) & banned)]
            if not first: continue
            name = " ".join(first)
        who = f"{name}, {aan(desc)}" if desc else name
        add(1, REL[r["prop"]].format(s=subj, x=who))
    v = clean_vals(f.get("P802"), banned)
    if v: add(1, f"{subj} taught {listing(v)}")
    v = [x for x in music(clean_vals(f.get("P166"), banned)) if not re.match(r"(?i)honorary", x)]
    if v: add(1, f"{subj} received the {v[0]}")
    v = clean_vals(f.get("P1066"), banned)
    if v: add(1, f"{subj} studied with {listing(v)}")
    v = music(clean_vals(f.get("P69"), banned))
    if v: add(2, f"{subj} studied at {the(v[0])}")
    v = [x for x in music(clean_vals(f.get("P108"), banned)) if not re.search(r"(?i)welte|victor|columbia|edison|aeolian|ampico|duo-art", x)]
    if v: add(2, f"{subj} worked at {the(v[0])}")
    v = music(clean_vals(f.get("P463"), banned))
    if v: add(2, f"{subj} was a member of {the(v[0])}")
    places = []
    for p in ("P937", "P551"):
        for x in clean_vals(f.get(p), banned):
            if x not in places: places.append(x)
    if len(places) >= 2: add(2, f"{subj} lived and worked in {listing(places, 3)}")
    elif places: add(2, f"{subj} worked in {places[0]}")
    v = [x for x in clean_vals(f.get("P800"), banned) if not re.match(r"(?i)(symphony|piano sonata|sonata|string quartet|piano concerto|concerto|piano trio|mass|requiem|études?|nocturnes?|preludes?|waltz(es)?)\b", x)]
    if v: add(2, f"{subj} is known for {listing(v)}")
    v = [x for x in clean_vals(f.get("P27"), banned) if not re.search(r"(?i)empire|kingdom|confederation|duchy|crown|congress|hamburg|bavaria|prussia|saxony|republic of|state of", x)] or []
    if len(v) >= 2: add(2, f"{subj} held citizenship of {listing(v, 3)}")      # a move abroad (Rachmaninoff, Prokofiev ...)
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
YEARS = {   # music only: premieres, deaths, recording milestones (checked by hand)
    1900: ["Puccini's Tosca had its premiere in Rome", "Elgar's The Dream of Gerontius had its premiere in Birmingham", "Charpentier's Louise had its premiere in Paris"],
    1901: ["Giuseppe Verdi died", "Rachmaninoff's Second Piano Concerto had its first complete performance", "Dvořák's Rusalka had its premiere in Prague"],
    1902: ["Debussy's Pelléas et Mélisande had its premiere in Paris", "Enrico Caruso made his first recordings, in Milan", "Cilea's Adriana Lecouvreur had its premiere in Milan"],
    1903: ["Hugo Wolf died", "Enrico Caruso made his debut at the Metropolitan Opera"],
    1904: ["Puccini's Madama Butterfly had its premiere at La Scala", "Antonín Dvořák died", "Janáček's Jenůfa had its premiere in Brno"],
    1905: ["Richard Strauss's Salome had its premiere in Dresden", "Debussy's La mer had its premiere", "Lehár's The Merry Widow had its premiere in Vienna"],
    1906: ["Victor introduced the Victrola", "Anton Arensky died", "the San Francisco earthquake struck while Caruso was singing there"],
    1907: ["Edvard Grieg died", "Gustav Mahler left the Vienna Court Opera"],
    1908: ["Gustav Mahler made his debut at the Metropolitan Opera", "Nikolai Rimsky-Korsakov died", "Pablo de Sarasate died"],
    1909: ["Rachmaninoff's Third Piano Concerto had its premiere in New York", "Richard Strauss's Elektra had its premiere in Dresden", "Isaac Albéniz died"],
    1910: ["Puccini's La fanciulla del West had its premiere at the Metropolitan Opera", "Stravinsky's The Firebird had its premiere in Paris", "Mahler's Eighth Symphony had its premiere in Munich"],
    1911: ["Gustav Mahler died", "Richard Strauss's Der Rosenkavalier had its premiere in Dresden", "Stravinsky's Petrushka had its premiere in Paris"],
    1912: ["Schoenberg's Pierrot lunaire had its premiere in Berlin", "Jules Massenet died", "Ravel's Daphnis et Chloé had its premiere in Paris"],
    1913: ["Stravinsky's The Rite of Spring had its riotous premiere in Paris"],
    1914: ["Vaughan Williams's A London Symphony had its premiere"],
    1915: ["Alexander Scriabin died", "Karl Goldmark died"],
    1916: ["Enrique Granados died when the Sussex was torpedoed", "Max Reger died"],
    1917: ["the first jazz record was made, by the Original Dixieland Jass Band", "Prokofiev wrote his Classical Symphony"],
    1918: ["Claude Debussy died", "Puccini's Il trittico had its premiere at the Metropolitan Opera", "Arrigo Boito died", "Prokofiev left Russia for America"],
    1919: ["Ruggero Leoncavallo died", "Elgar's Cello Concerto had its premiere in London"],
    1920: ["Max Bruch died", "Holst's The Planets had its first complete public performance"],
    1921: ["Enrico Caruso died", "Camille Saint-Saëns died", "Engelbert Humperdinck died"],
    1922: ["Ravel orchestrated Mussorgsky's Pictures at an Exhibition"],
    1923: ["Bartók wrote his Dance Suite", "Honegger's Pacific 231 had its premiere"],
    1924: ["Gershwin's Rhapsody in Blue had its premiere", "Giacomo Puccini died", "Gabriel Fauré died", "Ferruccio Busoni died"],
    1925: ["Victor and Columbia began making records with microphones (electrical recording)", "Berg's Wozzeck had its premiere in Berlin", "Erik Satie died"],
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
