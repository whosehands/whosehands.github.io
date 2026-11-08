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
        if "pianist" in desc or "conductor" in desc or "songwriter" in desc or "musician" in desc: score += 2
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
composers = json.load(open("data/composers.json", encoding="utf-8"))
out = {}
for c in composers:
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
        if "alt" in b and len(w["alt"]) < 6: w["alt"].add(b["alt"]["value"])
    out[c["name"]] = {"qid": qid, "label": hit.get("label"), "description": hit.get("description"),
                      "works": [{k: (sorted(v) if isinstance(v, set) else v) for k, v in w.items()} for w in works.values()]}
    print(c["name"], "->", qid, hit.get("label"), "|", len(works), "works", flush=True)
    time.sleep(2)
json.dump(out, open("sources/wikidata-works.json", "w", encoding="utf-8"), ensure_ascii=False)
print("done")
