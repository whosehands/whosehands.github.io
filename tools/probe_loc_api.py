"""One-off: look at what the loc.gov API returns for National Jukebox items not in the 1900-1922 dataset."""
import json, time, urllib.request, urllib.parse
UA = {"User-Agent": "WhoseHands-bot/1.0 (https://github.com/whosehands/whosehands.github.io)"}
def get(u):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=90) as r: return json.load(r)
        except Exception as e: print("retry", u, e, flush=True); time.sleep(15 * (i + 1))
out = {}
base = "https://www.loc.gov/collections/national-jukebox/"
out["search_1923_1925"] = get(base + "?" + urllib.parse.urlencode({"fo": "json", "c": "5", "dates": "1923/1925", "fa": "subject:opera"}))
time.sleep(4)
out["search_all_count"] = {k: v for k, v in (get(base + "?fo=json&c=1&at=pagination,facets") or {}).items()}
time.sleep(4)
first = ((out.get("search_1923_1925") or {}).get("results") or [{}])[0].get("id", "http://www.loc.gov/item/jukebox-21582/")
out["item"] = get(first.replace("http://", "https://").rstrip("/") + "/?fo=json")
json.dump(out, open("sources/loc-probe.json", "w"), indent=1)
print("done")
