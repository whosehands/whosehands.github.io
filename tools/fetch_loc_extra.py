"""Download National Jukebox listings that aren't in the Library of Congress's 1900-1922 dataset (data.labs.loc.gov/jukebox):
recordings from 1923-1925 (public domain in the US since 2024-2026) and recordings held by the Jukebox's other repositories.
Uses the public loc.gov JSON API, slowly. Writes sources/loc-jukebox-extra.jsonl in the dataset's own format, plus Audio_url.
"""
import json, re, time, urllib.parse, urllib.request
UA = {"User-Agent": "WhoseHands-bot/1.0 (https://github.com/whosehands/whosehands.github.io)"}
def get(u):
    for i in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=120) as r: return json.load(r)
        except Exception as e:
            print("retry", i, e, flush=True); time.sleep(20 * (i + 1))
    return None
have = set()
for line in open("sources/loc-jukebox-metadata.jsonl", encoding="utf-8"):
    have.add(json.loads(line)["Id"].rstrip("/").replace("https://", "http://"))
def role_of(parts):
    if len(parts) >= 3 and parts[1] == parts[2]: return parts[1]
    if parts[1] in ("Vocalist", "Instrumentalist"): return " -- ".join(parts[1:])
    return parts[1]
rows, seen = [], set()
for genre in ("opera", "classical music"):
    url = "https://www.loc.gov/collections/national-jukebox/?" + urllib.parse.urlencode({"fo": "json", "c": "150", "dates": "1900/1925", "fa": f"subject_genre:{genre}"})
    page = 0
    while url:
        d = get(url); page += 1
        if not d: print("gave up on", url); break
        for r in d.get("results", []):
            rid = (r.get("id") or "").rstrip("/").replace("https://", "http://")
            if not rid or rid in have or rid in seen: continue
            seen.add(rid)
            it = r.get("item") or {}
            media = [x.get("media") for x in r.get("resources") or [] if (x.get("media") or "").endswith(".mp3")]
            if not media: continue
            cons = []
            for c in it.get("contributors") or []:
                parts = [p.strip() for p in c.split(" -- ")]
                if len(parts) >= 2: cons.append({"Name": parts[0], "Role": role_of(parts)})
            loc = [x.title() for x in reversed(r.get("location") or [])]
            rows.append({"Id": rid + "/", "Url": r.get("url"), "Title": r.get("title"), "Date": it.get("recording_date") or r.get("date"),
                         "Description": r.get("description") or [], "Audio_type": it.get("audio_type"), "Contributors": cons,
                         "Genre": it.get("genre") or [], "Language": [x.title() for x in r.get("language") or []],
                         "Recording_label": it.get("recording_label"), "Recording_catalog_number": it.get("recording_catalog_number"),
                         "Location_text": ", ".join(loc[:2]) if loc else "", "Audio_url": media[0], "Repository": it.get("recording_repository")})
        print(genre, "page", page, "->", len(rows), "new so far", flush=True)
        url = (d.get("pagination") or {}).get("next")
        time.sleep(4)
with open("sources/loc-jukebox-extra.jsonl", "w", encoding="utf-8") as f:
    for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(len(rows), "recordings not in the dataset")
