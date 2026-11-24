"""Turn the hand-checked Wikimedia Commons picks into records for the catalog (run before build_records.py).

Reads data/commons-picks.json (file, performers, composer, title, years, label, genre: checked by hand against each file's
description), sources/commons-audio.json (license, description) and sources/commons-mp3.json (a playable MP3 for each file).
Skips a pick that's the same performance as a Library of Congress record already in the game.
Writes sources/commons-selected.json in the same shape as sources/loc-selected.json.
"""
import json, re, hashlib, unicodedata

def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except FileNotFoundError: return d
def fold(s): return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()
def words(s): return {w for w in re.findall(r"[a-z]+", fold(s)) if len(w) > 2}

picks = load("data/commons-picks.json", [])
audio = {a["title"]: a for a in load("sources/commons-audio.json", [])}
mp3 = load("sources/commons-mp3.json", {})
loc = load("sources/loc-selected.json", [])
GENRE = {"Opera & stage": ["Opera"], "Art songs": ["Classical music"], "Orchestral": ["Classical music"], "Piano music": ["Classical music"], "Instrumental solos": ["Classical music"]}
out, dupes, no_audio = [], 0, 0
for p in picks:
    url = mp3.get(p["file"])
    if not url: no_audio += 1; continue
    lead = p["performers"][0][0]
    tw = words(p["title"].split(":")[-1])
    same = [r for r in loc if any(fold(lead) == fold(n) or (len(lead.split()) > 1 and fold(lead.split()[-1]) == fold(n.split()[-1]) and fold(lead.split()[0])[0] == fold(n.split()[0])[0]) for n, _ in r["performers"]) and tw and len(tw & words(r["title"])) * 3 >= 2 * len(tw)
            and abs(r["year"] - p["yearMin"]) <= 1]
    if same: dupes += 1; continue
    # name it the way the Library of Congress records are named, so the same aria isn't two answers ("Un bel di" / "Un bel dì vedremo"):
    # the aria's own title (the build then files it under its opera like the others), or an existing record's title for it
    part = p["title"].split(":", 1)[-1].strip()
    w2 = lambda x: {w for w in re.findall(r"[a-z]+", fold(x)) if len(w) > 1}
    title = part if ":" in p["title"] and p["genre"] == "Opera & stage" else p["title"]
    for r in loc:
        if r["composers"][:1] == [p["composer"]]:
            a_, b_ = w2(part), w2(r["title"])
            if len(a_) >= 2 and len(b_) >= 2 and (a_ <= b_ or b_ <= a_): title = r["title"]; break
    a = audio.get(p["file"], {})
    name = p["file"].split(":", 1)[1]
    out.append({
        "id": "wmc-" + hashlib.md5(p["file"].encode()).hexdigest()[:10],
        "audio": url, "performers": p["performers"], "credits": [], "composers": [p["composer"]],
        "title": title, "year": p["yearMin"], "yearMax": p["yearMax"], "date": str(p["yearMin"]), "place": "",
        "label": p["label"] or "Historical", "catalog": "", "format": (p["label"] + " recording") if p["label"] else "Historical recording",
        "source": "https://commons.wikimedia.org/wiki/File:" + name.replace(" ", "_"), "license": a.get("license") or "Public domain",
        "genres": GENRE.get(p["genre"], []), "genreHint": "Songs" if p["genre"] == "Art songs" else p["genre"], "artSong": p["genre"] == "Art songs",
    })
json.dump(out, open("sources/commons-selected.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(out), "Commons recordings;", dupes, "skipped as Library of Congress duplicates;", no_audio, "without a playable MP3 yet")
