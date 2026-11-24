"""List early classical recordings on Europeana (europeana.eu). Runs on GitHub Actions with the EUROPEANA_KEY secret.

Searches sound items dated 1895-1925 whose rights allow reuse (Europeana's "open" and "restricted" groups: public domain,
CC0, CC BY, CC BY-SA, and non-commercial licenses), using music words in several languages and composer names.
Writes sources/europeana-audio.json: title, people, year, rights, provider, media URL, landing page, description, subjects.
Then checks that each item's audio file really plays (some providers moved their files or block automated requests) and
writes sources/europeana-media.json: {item id: working https URL, or "" when none answered}. --verify runs only that check.
"""
import json, os, re, sys, time, urllib.parse, urllib.request
# (the API adds the key to its "guid" links, so only the part before "?" is kept)

def verify():
    try: items = json.load(open("sources/europeana-audio.json", encoding="utf-8"))
    except FileNotFoundError: return
    try: known = json.load(open("sources/europeana-media.json", encoding="utf-8"))
    except FileNotFoundError: known = {}
    hdr = {"User-Agent": "Mozilla/5.0 (compatible; WhoseHands-bot/1.0; +https://github.com/whosehands/whosehands.github.io)", "Range": "bytes=0-2047"}
    ok = 0
    for it in items:
        m = it.get("media") or ""
        if not m or it["provider"].startswith("Westphalian") or known.get(it["id"]): ok += bool(known.get(it["id"])); continue
        m = re.sub(r"^http://", "https://", m)
        tries = [m.replace("phonobase.org/audio/", "phonobase.org/audios/"), m] if "phonobase.org/audio/" in m else [m]
        known[it["id"]] = ""
        for u in tries:
            try:
                with urllib.request.urlopen(urllib.request.Request(u, headers=hdr), timeout=60) as r:
                    head = r.read(2048)
                    if r.status in (200, 206) and (re.search(r"audio|mpeg|ogg", r.headers.get("Content-Type", "")) or head[:3] == b"ID3" or head[:2] == b"\xff\xfb"):
                        known[it["id"]] = r.geturl(); ok += 1; break
            except Exception: pass
        time.sleep(0.3)
    json.dump(known, open("sources/europeana-media.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(ok, "items with a playable audio file", flush=True)
if "--verify" in sys.argv: verify(); sys.exit()

KEY = os.environ.get("EUROPEANA_KEY", "").strip()
if not KEY: sys.exit("EUROPEANA_KEY is not set")
UA = {"User-Agent": "WhoseHands-bot/1.0 (https://github.com/whosehands/whosehands.github.io)", "X-Api-Key": KEY}
def get(params, tries=5):
    url = "https://api.europeana.eu/record/v2/search.json?" + urllib.parse.urlencode(params, doseq=True)
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r: return json.load(r)
        except Exception as e:
            print("retry", i, str(e)[:200], flush=True); time.sleep(10 * (i + 1))
    return None

WORDS = ["opera", "oper", "opéra", "aria", "arie", "air", "romanza", "romance", "cavatina", "lied", "lieder", "mélodie", "chanson", "song",
         "symphony", "sinfonie", "symphonie", "sinfonia", "overture", "ouverture", "concerto", "konzert", "sonata", "sonate",
         "piano", "klavier", "pianoforte", "violin", "violine", "violon", "violino", "cello", "orchestra", "orchester", "orchestre",
         "tenor", "ténor", "tenore", "soprano", "sopran", "baritone", "bariton", "baritono", "bass", "basso", "contralto", "alt",
         "nocturne", "prelude", "prélude", "étude", "walzer", "valse", "polonaise", "mazurka", "rhapsody", "ballade", "serenade", "ständchen"]
comps = []
try: comps = [r["composer"].split()[-1] for r in json.load(open("data/catalog.json", encoding="utf-8"))["recordings"] if r.get("composerFame") in ("famous", "known")]
except Exception: pass
QUERIES = WORDS + sorted(set(comps))[:300]
seen, out = set(), []
for q in QUERIES:
    cursor, n = "*", 0
    while cursor and n < 20:                      # at most 2,000 items per query word
        d = get({"query": q, "qf": ["TYPE:SOUND", "YEAR:[1895 TO 1925]"], "reusability": ["open", "restricted"], "rows": "100", "cursor": cursor, "profile": "rich"})
        if not d or not d.get("success", True): print("failed", q, d and d.get("error")); break
        for it in d.get("items", []):
            if it["id"] in seen: continue
            seen.add(it["id"])
            first = lambda k: (it.get(k) or [""])[0] if isinstance(it.get(k), list) else (it.get(k) or "")
            lang = lambda k: [v for vals in (it.get(k) or {}).values() for v in vals] if isinstance(it.get(k), dict) else (it.get(k) or [])
            out.append({"id": it["id"], "title": first("title"), "titles": (it.get("title") or [])[:4], "creators": (it.get("dcCreator") or [])[:8],
                        "contributors": lang("dcContributorLangAware")[:8], "year": (it.get("year") or [""])[0], "rights": first("rights"),
                        "provider": first("dataProvider"), "aggregator": first("provider"), "media": first("edmIsShownBy"), "page": first("edmIsShownAt"),
                        "europeana": (it.get("guid") or "").split("?")[0], "description": " ".join(lang("dcDescriptionLangAware") or it.get("dcDescription") or [])[:700],
                        "subjects": lang("dcSubjectLangAware")[:10], "language": (it.get("language") or [])[:3], "query": q})
        n += 1
        cursor = d.get("nextCursor")
        time.sleep(0.5)
    print(q, "->", len(out), "items so far", flush=True)
json.dump(out, open("sources/europeana-audio.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(len(out), "items written")
verify()
