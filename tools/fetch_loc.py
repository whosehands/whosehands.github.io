"""Download the Library of Congress National Jukebox listing (public-domain Victor recordings).
Runs on GitHub Actions. Writes sources/loc-jukebox.jsonl, one recording per line."""
import json, time, urllib.request, urllib.parse, sys
BASE = "https://www.loc.gov/collections/national-jukebox/"
UA = {"User-Agent": "WhoseHands-bot (github.com/concord-mass/concord-mass.github.io)"}
def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except Exception as e:
            print("retry", i, url, e, file=sys.stderr); time.sleep(5 * (i + 1))
    raise SystemExit("failed: " + url)
KEEP = ("id", "title", "date", "dates", "contributor", "contributor_names", "subject", "genre", "original_format", "partof",
        "resources", "item", "language", "notes", "number", "url", "online_format", "description", "location")
out = open("sources/loc-jukebox.jsonl", "w", encoding="utf-8")
page, n = 1, 0
while True:
    q = {"fo": "json", "c": "100", "sp": str(page), "dates": "1900/1925",
         "fa": "partof_repository:recorded sound section, library of congress"}
    data = get(BASE + "?" + urllib.parse.urlencode(q))
    for r in data.get("results", []):
        out.write(json.dumps({k: r.get(k) for k in KEEP if k in r}, ensure_ascii=False) + "\n"); n += 1
    pg = data.get("pagination", {})
    print("page", page, "of", pg.get("total"), "items so far", n)
    if not pg.get("next"): break
    page += 1; time.sleep(2)
out.close()
print("done", n)
