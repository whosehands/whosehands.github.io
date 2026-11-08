"""Download every known work by each composer in data/composers.json from Wikidata (CC0).
Runs on GitHub Actions. Writes sources/wikidata-works.json."""
import json, time, urllib.request, urllib.parse, sys, re
UA = {"User-Agent": "WhoseHands-bot/1.0 (https://github.com/whosehands/whosehands.github.io)"}
def get(url, tries=5):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return json.load(r)
        except Exception as e:
            print("retry", i, e, flush=True); time.sleep(10 * (i + 1))
    return None
def search(name):
    q = {"action": "wbsearchentities", "search": name, "language": "en", "type": "item", "limit": "10", "format": "json"}
    d = get("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(q)) or {}
    return d.get("search", [])
def sparql(query):
    d = get("https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": query, "format": "json"}))
    return (d or {}).get("results", {}).get("bindings", [])
def years(dates):
    return re.findall(r"1[6-9]\d\d|20\d\d", dates or "")
def find_composer(name, dates):
    cands = search(name)
    if not cands:  # try surname + given initial forms
        cands = search(name.split()[-1])
    ys = years(dates)
    best = None
    for c in cands:
        desc = (c.get("description") or "").lower()
        score = 0
        if "composer" in desc: score += 3
        if re.search(r"pianist|conductor|songwriter|musician|singer|soprano|mezzo|tenor|baritone|bass|contralto|violinist|cellist|harpsichordist|organist|orchestra|ensemble|harpist|flautist|flutist|xylophon|cornet", desc): score += 2
        if re.search(r"orchestra|philharmonic", name.lower()) and re.search(r"orchestra|ensemble", desc): score += 3
        if any(y in desc for y in ys): score += 4
        if best is None or score > best[0]: best = (score, c)
    return best[1] if best and best[0] >= 2 else None
Q = """SELECT ?w ?wLabel ?cat ?catLabel ?formLabel ?genreLabel ?partOf ?date ?alt WHERE {
  ?w wdt:P86 wd:%s .
  OPTIONAL { ?w p:P528 ?cs . ?cs ps:P528 ?cat . OPTIONAL { ?cs pq:P972 ?catq . } }
  OPTIONAL { ?w wdt:P31 ?form . }
  OPTIONAL { ?w wdt:P136 ?genre . }
  OPTIONAL { ?w wdt:P361 ?partOf . }
  OPTIONAL { ?w wdt:P577 ?date . }
  OPTIONAL { ?w skos:altLabel ?alt . FILTER(LANG(?alt) = "en") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr,de,it,ru,pl,cs,hu,es,nl,sv,nb,fi". }
} LIMIT 20000"""
def sitelinks(qid):
    q = {"action": "wbgetentities", "ids": qid, "props": "sitelinks", "format": "json"}
    d = get("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(q)) or {}
    return len(((d.get("entities") or {}).get(qid) or {}).get("sitelinks") or {})
QL = """SELECT ?w (GROUP_CONCAT(DISTINCT ?l; separator="|") AS ?names) WHERE {
  ?w wdt:P86 wd:%s . ?w rdfs:label ?l . FILTER(LANG(?l) IN ("en","de","fr","it","pl","ru","cs","hu","es","nl","nb","sv"))
} GROUP BY ?w"""
composers = json.load(open("data/composers.json", encoding="utf-8"))
def load(path):
    try: return json.load(open(path, encoding="utf-8"))
    except Exception: return {}
out = load("sources/wikidata-works.json")          # reuse earlier lookups; only new names are fetched
for c in composers:
    if c["name"] in out and (out[c["name"]] is None or out[c["name"]].get("v") == 2): continue
    hit = find_composer(c["name"], c.get("dates", ""))
    if not hit:
        print("no match:", c["name"], flush=True); out[c["name"]] = None; time.sleep(1); continue
    qid = hit["id"]
    rows = sparql(Q % qid)
    works = {}
    for b in rows:
        wid = b["w"]["value"].rsplit("/", 1)[-1]
        w = works.setdefault(wid, {"id": wid, "label": b.get("wLabel", {}).get("value", ""), "catalog": set(), "forms": set(), "genres": set(), "partOf": set(), "date": "", "alt": set()})
        if "cat" in b: w["catalog"].add(b["cat"]["value"])
        if "formLabel" in b: w["forms"].add(b["formLabel"]["value"])
        if "genreLabel" in b: w["genres"].add(b["genreLabel"]["value"])
        if "partOf" in b: w["partOf"].add(b["partOf"]["value"].rsplit("/", 1)[-1])
        if "date" in b and not w["date"]: w["date"] = b["date"]["value"][:4]
        if "alt" in b and len(w["alt"]) < 8: w["alt"].add(b["alt"]["value"])
    for b in sparql(QL % qid):   # the work's title in other languages, to match catalog titles like "Studien nach Capricen von Paganini"
        wid = b["w"]["value"].rsplit("/", 1)[-1]
        if wid in works: works[wid]["alt"] |= set(b.get("names", {}).get("value", "").split("|")) - {""}
    out[c["name"]] = {"v": 2, "qid": qid, "label": hit.get("label"), "description": hit.get("description"), "sitelinks": sitelinks(qid),
                      "works": [{k: (sorted(v) if isinstance(v, set) else v) for k, v in w.items()} for w in works.values()]}
    print(c["name"], "->", qid, hit.get("label"), "|", len(works), "works", flush=True)
    time.sleep(0.5)
json.dump(out, open("sources/wikidata-works.json", "w", encoding="utf-8"), ensure_ascii=False)

# performers: who they are and how well known
people = load("sources/wikidata-people.json")
for p in json.load(open("data/performers.json", encoding="utf-8")):
    if p["name"] in people: continue
    hit = find_composer(p["name"], p.get("dates", ""))
    if not hit: people[p["name"]] = None; print("no match:", p["name"], flush=True); time.sleep(1); continue
    people[p["name"]] = {"qid": hit["id"], "label": hit.get("label"), "description": hit.get("description"), "sitelinks": sitelinks(hit["id"])}
    print(p["name"], "->", hit["id"], people[p["name"]]["sitelinks"], flush=True); time.sleep(0.3)
json.dump(people, open("sources/wikidata-people.json", "w", encoding="utf-8"), ensure_ascii=False)
print("done")
