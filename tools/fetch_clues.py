"""Download the facts used for quiz-bowl style clues. Runs on GitHub Actions.

For every performer, composer and piece in data/catalog.json:
  sources/clue-facts.json   Wikidata statements (CC0): teachers, pupils, birthplace, premiere, librettist, dedicatee ...
  sources/clue-wiki.json    the English Wikipedia article text (CC BY-SA 4.0), for clue sentences
  sources/clue-search.json  pieces with no Wikidata link yet: the Wikipedia article found by searching, if any
Keeps what earlier runs found and only fetches what's new.
"""
import json, os, re, time, urllib.parse, urllib.request

UA = {"User-Agent": "WhoseHands-bot/1.0 (https://github.com/whosehands/whosehands.github.io)"}
def get(url, tries=5):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return json.load(r)
        except Exception as e:
            print("retry", i, e, flush=True); time.sleep(8 * (i + 1))
    return None
def load(p):
    try: return json.load(open(p, encoding="utf-8"))
    except FileNotFoundError: return {}
def sparql(q):
    d = get("https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": q, "format": "json"}))
    return (d or {}).get("results", {}).get("bindings", [])
def wiki(params):
    return get("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"})) or {}

cat = json.load(open("data/catalog.json", encoding="utf-8"))
people = load("sources/wikidata-people.json")
works = load("sources/wikidata-works.json")
facts, texts, found = load("sources/clue-facts.json"), load("sources/clue-wiki.json"), load("sources/clue-search.json")

# 1. pieces with no Wikidata link: search Wikipedia for "<title> <composer>" and keep a hit only if its article names the composer
for r in cat["recordings"]:
    k = r["pieceKey"]
    if r.get("workQid") or k in found: continue
    sn, title = (r["piece"].split(" – ", 1) + [""])[:2]
    title = re.sub(r"\s*\([^)]*\)", "", title).strip()
    if not title or sn == "Traditional": found[k] = None; continue
    res = wiki({"action": "query", "list": "search", "srsearch": f'{title} {sn}', "srlimit": "3"}).get("query", {}).get("search", [])
    hit = None
    for h in res:
        page = wiki({"action": "query", "prop": "extracts|pageprops", "exintro": "1", "explaintext": "1", "titles": h["title"], "redirects": "1"}).get("query", {}).get("pages", [{}])[0]
        intro = (page.get("extract") or "").lower()
        tw = [w for w in re.findall(r"\w+", title.lower()) if len(w) > 3]
        if sn.lower().split("-")[0] in intro[:600] and (not tw or sum(w in (h["title"] + " " + intro[:300]).lower() for w in tw) >= max(1, len(tw) // 2)):
            hit = {"title": page.get("title"), "qid": (page.get("pageprops") or {}).get("wikibase_item")}
            break
        time.sleep(0.2)
    found[k] = hit
    print("search", r["piece"], "->", hit and hit["title"], flush=True)
    time.sleep(0.3)
json.dump(found, open("sources/clue-search.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)

# 2. which Wikidata items to describe
want = set()
for r in cat["recordings"]:
    if r.get("workQid"): want.add(r["workQid"])
    hit = found.get(r["pieceKey"])
    if hit and hit.get("qid"): want.add(hit["qid"])
    for p in r["performers"]:
        v = people.get(p)
        if v and v.get("qid"): want.add(v["qid"])
    v = works.get(r["composer"])
    if v and v.get("qid"): want.add(v["qid"])
todo = sorted(q for q in want if q not in facts)
PROPS = {"P19": "born in", "P20": "died in", "P119": "buried at", "P1066": "student of", "P802": "teacher of", "P69": "educated at",
         "P26": "spouse", "P166": "award", "P412": "voice type", "P1303": "instrument", "P108": "employer", "P463": "member of",
         "P27": "citizen of", "P569": "born", "P570": "died", "P22": "father", "P25": "mother", "P40": "child", "P3373": "sibling",
         "P737": "influenced by", "P937": "worked in", "P551": "lived in", "P800": "notable work", "P1449": "nickname",
         "P86": "composer", "P87": "librettist", "P676": "lyrics by", "P571": "written", "P1191": "premiered", "P4647": "premiere place",
         "P144": "based on", "P825": "dedicated to", "P826": "key", "P407": "language", "P840": "set in", "P674": "characters",
         "P361": "part of", "P136": "genre", "P31": "instance of", "P1476": "title", "P138": "named after", "P921": "subject",
         "P710": "participant", "P175": "performer", "P1877": "after a work by", "P50": "author"}
for i in range(0, len(todo), 60):
    batch = todo[i:i + 60]
    q = """SELECT ?item ?prop ?val ?valLabel WHERE {
      VALUES ?item { %s }
      VALUES ?prop { %s }
      ?item ?prop ?val .
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr,de,it". }
    }""" % (" ".join("wd:" + x for x in batch), " ".join("wdt:" + p for p in PROPS))
    rows = sparql(q)
    for x in batch: facts[x] = {"_label": None}
    for b in rows:
        item = b["item"]["value"].rsplit("/", 1)[-1]; prop = b["prop"]["value"].rsplit("/", 1)[-1]
        val = b.get("valLabel", b["val"])["value"]
        if re.match(r"^Q\d+$", val): continue                    # no readable name
        lst = facts[item].setdefault(prop, [])
        if val not in lst and len(lst) < 12: lst.append(val)
    q2 = """SELECT ?item ?itemLabel ?itemDescription ?title WHERE {
      VALUES ?item { %s }
      OPTIONAL { ?a schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> ; schema:name ?title . }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
    }""" % " ".join("wd:" + x for x in batch)
    for b in sparql(q2):
        item = b["item"]["value"].rsplit("/", 1)[-1]
        facts[item]["_label"] = b.get("itemLabel", {}).get("value")
        facts[item]["_description"] = b.get("itemDescription", {}).get("value")
        if "title" in b: facts[item]["_enwiki"] = b["title"]["value"]
    print("facts", i + len(batch), "/", len(todo), flush=True)
    time.sleep(1)
# 2b. relatives and partners. Simple queries (one big one times out); tools/build_clues.py keeps only those who worked in music
#     or were married to a composer (Liszt's daughter Cosima).
MUSIC_JOB = re.compile(r"(?i)music|compos|singer|soprano|tenor|baritone|contralto|mezzo|pian|violin|cell|organ|harp|conduct|librett|impresario|opera|theatre director|critic|choir|song")
people_q = sorted(q for q in want if q in facts and "_relatives" not in facts[q] and (facts[q].get("P569") or facts[q].get("P19")))
for i in range(0, len(people_q), 80):
    batch = people_q[i:i + 80]
    d = get("https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"format": "json", "query": """SELECT ?item ?prop ?rel WHERE {
      VALUES ?item { %s } VALUES ?prop { wdt:P26 wdt:P451 wdt:P22 wdt:P25 wdt:P40 wdt:P3373 wdt:P1038 } ?item ?prop ?rel . }""" % " ".join("wd:" + x for x in batch)}), tries=3)
    if d is None: print("relatives query failed; will retry next run", flush=True); continue
    links = [(b["item"]["value"].rsplit("/", 1)[-1], b["prop"]["value"].rsplit("/", 1)[-1], b["rel"]["value"].rsplit("/", 1)[-1]) for b in d["results"]["bindings"]]
    rels = sorted({r for _, _, r in links if re.match(r"^Q\d+$", r)})
    info = {r: {"name": None, "occupations": [], "marriedTo": []} for r in rels}
    ok = True
    for j in range(0, len(rels), 80):
        vals = " ".join("wd:" + x for x in rels[j:j + 80])
        d1 = get("https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"format": "json", "query": """SELECT ?rel ?relLabel ?occLabel WHERE {
          VALUES ?rel { %s } OPTIONAL { ?rel wdt:P106 ?occ . } SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr,de,it". } }""" % vals}), tries=3)
        d2 = get("https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"format": "json", "query": """SELECT ?rel ?viaLabel WHERE {
          VALUES ?rel { %s } ?rel wdt:P26|wdt:P451 ?via . ?via wdt:P106 wd:Q36834 . SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr,de,it". } }""" % vals}), tries=3)
        if d1 is None or d2 is None: ok = False; break
        for b in d1["results"]["bindings"]:
            x = info[b["rel"]["value"].rsplit("/", 1)[-1]]
            x["name"] = b.get("relLabel", {}).get("value")
            o = b.get("occLabel", {}).get("value")
            if o and o not in x["occupations"] and not re.match(r"^Q\d+$", o): x["occupations"].append(o)
        for b in d2["results"]["bindings"]:
            v = b.get("viaLabel", {}).get("value")
            if v: info[b["rel"]["value"].rsplit("/", 1)[-1]]["marriedTo"].append(v)
        time.sleep(1)
    if not ok: print("relatives details failed; will retry next run", flush=True); continue
    for x in batch: facts[x]["_relatives"] = []
    for item, prop, r in links:
        x = info.get(r)
        if not x or not x["name"] or re.match(r"^Q\d+$", x["name"]): continue
        musical = [o for o in x["occupations"] if MUSIC_JOB.search(o)]
        married = [m for m in x["marriedTo"] if m != facts[item].get("_label")]
        if musical or married:
            facts[item]["_relatives"].append({"prop": prop, "name": x["name"], "occupations": musical[:3], "marriedTo": married[:2]})
    print("relatives", i + len(batch), "/", len(people_q), flush=True)
    time.sleep(1)
json.dump(facts, open("sources/clue-facts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)

# 3. Wikipedia article text for everything that has one
titles = {v.get("_enwiki") for v in facts.values() if v.get("_enwiki")} | {h["title"] for h in found.values() if h and h.get("title")}
for t in sorted(titles):
    if t in texts: continue
    page = wiki({"action": "query", "prop": "extracts", "explaintext": "1", "exsectionformat": "wiki", "titles": t, "redirects": "1"}).get("query", {}).get("pages", [{}])[0]
    texts[t] = (page.get("extract") or "")[:20000]
    print("wiki", t, len(texts[t]), flush=True)
    time.sleep(0.4)
json.dump(texts, open("sources/clue-wiki.json", "w", encoding="utf-8"), ensure_ascii=False)
print("done:", len(facts), "items,", len(texts), "articles")
