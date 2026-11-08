"""Add the selected Library of Congress records to data/catalog.json (run after build_catalog.py)."""
import json, re
CAT = "data/catalog.json"
cat = json.load(open(CAT, encoding="utf-8"))
sel = json.load(open("sources/loc-selected.json", encoding="utf-8"))
cat["recordings"] = [r for r in cat["recordings"] if r.get("kind") != "record"]
try: wd = json.load(open("sources/wikidata-works.json", encoding="utf-8"))
except FileNotFoundError: wd = {}
def classical_composer(name):
    """A composer in the classical tradition, known well enough (20+ Wikipedia languages)."""
    v = wd.get(name)
    if not v: return False
    d = (v.get("description") or "").lower()
    return "composer" in d and not re.search(r"songwriter|popular|vaudeville|hymn|gospel|ragtime|tin pan|lyricist|bandleader", d) and (v.get("sitelinks") or 0) >= 20
def art_song(r):
    g = set(r["genres"])
    return bool(g & {"Classical music", "Classical"}) and not (g & {"Popular music", "Religious", "Ethnic music", "Musical theater"}) \
        and bool(r["composers"]) and classical_composer(r["composers"][0])
def surname(n):
    """Conventional short name: 'Ludwig van Beethoven' -> 'Beethoven', 'Reginald De Koven' -> 'De Koven'."""
    n = re.sub(r"\s*\(.*?\)", "", n).strip()
    parts = n.split()
    if len(parts) >= 2 and parts[-2] in ("De", "Di", "Da", "Del", "Van", "La", "Le", "Mac", "Mc"): return " ".join(parts[-2:])
    return parts[-1] if parts else n
def genre_hint(r):
    roles = {x for _, x in r["performers"]}
    g = set(r["genres"])
    if "Opera" in g: return "Opera & stage"
    if roles <= {"orchestra", "conductor"}: return "Orchestral"
    if roles <= {"piano"}: return "Piano music"
    if roles & {"soprano", "tenor", "baritone", "bass", "contralto", "mezzo-soprano", "vocalist", "chorus"}: return "Songs"
    return "Instrumental solos"
for r in sel:
    comp = r["composers"][0] if r["composers"] else "Traditional"
    sn = surname(comp) if comp != "Traditional" else "Traditional"
    title = re.sub(r"\s+", " ", r["title"]).strip().rstrip(".")
    title = title[:1].upper() + title[1:]
    cat["recordings"].append({
        "id": r["id"], "kind": "record", "audio": r["audio"],
        "performers": [p for p, _ in r["performers"]], "roles": [x for _, x in r["performers"]],
        "performerDates": {}, "credits": "; ".join(r["credits"]),
        "composer": comp, "composerDates": "", "otherComposers": r["composers"][1:],
        "piece": f"{sn} – {title}", "work": f"{sn} – {title}", "part": "", "title": title, "rollLabel": "",
        "yearMin": r["year"], "yearMax": r["year"], "yearExact": True, "date": r["date"],
        "place": r["place"], "label": r["label"], "format": f"{r['label']} 78 record" + (f" no. {r['catalog']}" if r.get("catalog") else ""),
        "rollNumber": "", "source": r["source"], "license": "Public domain (US)", "genreHint": genre_hint(r), "artSong": genre_hint(r) == "Songs" and art_song(r), "famous": False,
    })
json.dump(cat, open(CAT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(sum(1 for r in cat["recordings"] if r.get("kind") == "record"), "records added;", len(cat["recordings"]), "recordings in total")
