"""List historical classical recordings on Wikimedia Commons. Runs on GitHub Actions.

Walks audio categories (a few levels down), keeps audio files whose license is public domain or a free Creative Commons
license, and writes sources/commons-audio.json with each file's title, url, license, date, description and categories.
Run: python3 tools/fetch_commons.py
"""
import json, re, time, urllib.parse, urllib.request

UA = {"User-Agent": "WhoseHands-bot/1.0 (https://github.com/whosehands/whosehands.github.io)"}
API = "https://commons.wikimedia.org/w/api.php?"
def get(params, tries=5):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(API + urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"}), headers=UA), timeout=90) as r:
                return json.load(r)
        except Exception as e:
            print("retry", i, e, flush=True); time.sleep(5 * (i + 1))
    return {}

ROOTS = ["Category:Audio files of opera", "Category:Audio files of classical music", "Category:Audio files of piano music", "Category:Historical sound recordings",
         "Category:Edison Records", "Category:Victor Records", "Category:Columbia Records", "Category:Gramophone Company", "Category:Odeon Records",
         "Category:Pathé Records", "Category:Fonotipia Records", "Category:Zonophone Records", "Category:Audio files of 78 rpm records",
         "Category:Opera singers - audio files", "Category:Audio files of art songs", "Category:Audio files of songs by Franz Schubert",
         "Category:Phonograph cylinders", "Category:Audio files of violin music", "Category:Audio files of orchestral music",
         "Category:Recordings of Enrico Caruso", "Category:Audio files by year of recording", "Category:1900s audio recordings", "Category:1910s audio recordings",
         "Category:1920s audio recordings", "Category:Sound recordings by decade"]
AUDIO = re.compile(r"\.(ogg|oga|opus|flac|mp3|wav|webm)$", re.I)
SKIP_CAT = re.compile(r"(?i)speech|spoken|podcast|interview|birds?|animal|wikipedia|pronunciation|lingua|language|poetry|news|radio|jazz|blues|ragtime|country|folk|hymn|anthem|military|film|television|game")
seen_cats, files = set(), {}
queue = [(c, 0) for c in ROOTS]
while queue:
    cat, depth = queue.pop(0)
    if cat in seen_cats or len(seen_cats) > 3000: continue
    seen_cats.add(cat)
    cont = {}
    while True:
        d = get({"action": "query", "list": "categorymembers", "cmtitle": cat, "cmlimit": "500", "cmtype": "file|subcat", **cont})
        for m in d.get("query", {}).get("categorymembers", []):
            t = m["title"]
            if t.startswith("Category:"):
                if depth < 3 and not SKIP_CAT.search(t): queue.append((t, depth + 1))
            elif AUDIO.search(t): files.setdefault(t, set()).add(cat)
        if "continue" not in d: break
        cont = d["continue"]
    time.sleep(0.2)
print(len(seen_cats), "categories,", len(files), "audio files", flush=True)

out = []
names = sorted(files)
for i in range(0, len(names), 40):
    batch = names[i:i + 40]
    d = get({"action": "query", "titles": "|".join(batch), "prop": "imageinfo|categories", "iiprop": "url|extmetadata|size|mime", "cllimit": "max",
             "iiextmetadatafilter": "LicenseShortName|License|DateTimeOriginal|ImageDescription|Artist|Credit|ObjectName|UsageTerms"})
    for p in d.get("query", {}).get("pages", []):
        ii = (p.get("imageinfo") or [{}])[0]
        md = {k: re.sub(r"<[^>]+>", "", (v or {}).get("value", "")).strip() for k, v in (ii.get("extmetadata") or {}).items()}
        lic = md.get("LicenseShortName", "") + " " + md.get("License", "")
        if not re.search(r"(?i)public domain|pd|cc0|cc[- ]by(?![- ]?nc)", lic) or re.search(r"(?i)\bnc\b|non-?commercial|fair use", lic): continue
        out.append({"title": p["title"], "url": ii.get("url"), "mime": ii.get("mime"), "seconds": ii.get("duration"), "license": md.get("LicenseShortName"),
                    "date": md.get("DateTimeOriginal", "")[:120], "description": md.get("ImageDescription", "")[:600], "artist": md.get("Artist", "")[:200],
                    "credit": md.get("Credit", "")[:300], "name": md.get("ObjectName", "")[:200],
                    "categories": [c["title"] for c in p.get("categories", [])][:30]})
    time.sleep(0.3)
json.dump(out, open("sources/commons-audio.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(len(out), "freely licensed audio files written")
