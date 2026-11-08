"""Pick the classical, opera and piano records from the Library of Congress dataset and describe their performers.
Writes sources/loc-selected.json (one entry per record)."""
import json, re, collections, sys
rows = [json.loads(l) for l in open("sources/loc-jukebox-metadata.jsonl", encoding="utf-8")]
audio = {}
for line in open("sources/loc-jukebox-manifest.txt", encoding="utf-8"):
    f = line.rstrip("\n").split("\t")
    if len(f) >= 5 and f[0].endswith("_1.mp3"): audio[f[1].rstrip("/")] = "https://" + f[4]
HOUSE = re.compile(r"^(victor|victor concert|victor symphony|victor salon|victor light opera|victor opera|victor mixed|victor male|victor female|victor brass|victor string|victor dance|victor military)\b|orchestra$|^orchestra|chorus$|quartet$", re.I)
HOUSE_COND = {"Rogers, Walter B.", "Pasternack, Josef", "Bourdon, Rosario", "Shilkret, Nathaniel", "Pryor, Arthur", "Paul, [?]"}
REAL_ORCH = re.compile(r"philadelphia|boston symphony|new york philharmonic|symphony society|metropolitan opera|la scala|royal opera|berlin|london symphony|chicago symphony|cincinnati|minneapolis|st\. louis|detroit|san francisco", re.I)
SOLO = re.compile(r"^(Vocalist|Instrumentalist)")
def flip(n):
    n = re.sub(r"\s*\[\?\]", "", n).strip()
    if ", " in n and not re.search(r"\b(band|orchestra|company|quartet|chorus|choir|society|ensemble|trio)\b", n, re.I):
        last, first = n.split(", ", 1); return f"{first} {last}".strip()
    return n
def role(r):
    r = r.split("-- ")[-1].replace(" Vocal", "").lower()
    return {"musical group": "orchestra", "vocal group": "chorus", "leader": "conductor"}.get(r, r)
out, why = [], collections.Counter()
for r in rows:
    genres = set(r.get("Genre") or [])
    if not genres & {"Opera", "Classical music", "Classical"}: why["genre"] += 1; continue
    if genres & {"Ethnic characterizations", "Humorous songs", "Comedies", "Monologues, dialogues, and recitations"}: why["comedy"] += 1; continue
    if r.get("Audio_type") == "Spoken": why["spoken"] += 1; continue
    t = r.get("Title") or ""
    if re.search(r"(?i)\bgems from|medley|selections?\b|potpourri|fantasia on|reminiscences of", t): why["medley"] += 1; continue
    a = audio.get(r["Id"].rstrip("/"))
    if not a: why["no audio"] += 1; continue
    cons = r.get("Contributors") or []
    composers = [flip(c["Name"]) for c in cons if c["Role"] in ("Composer", "Songwriter")]
    groups = [c for c in cons if c["Role"] in ("Musical Group", "Vocal Group")]
    if any(re.search(r"\bband\b", c["Name"], re.I) for c in groups): why["band"] += 1; continue
    soloists = [c for c in cons if SOLO.match(c["Role"])]
    conductors = [c for c in cons if c["Role"] in ("Conductor", "Leader")]
    perf, credits = [], []
    desc = " ".join(r.get("Description") or []).lower()
    for c in soloists:
        rl = role(c["Role"])
        if "obligato" in desc and rl in ("cello", "violin", "flute", "harp") and len(soloists) > 1 and c["Name"] in HOUSE_COND: credits.append(f"{flip(c['Name'])} ({rl})"); continue
        perf.append((flip(c["Name"]), rl))
    real_orch = [g for g in groups if REAL_ORCH.search(g["Name"]) or not HOUSE.search(g["Name"])]
    if not perf:   # orchestral record: the orchestra and its conductor are the performers
        perf += [(flip(g["Name"]), "orchestra") for g in groups]
        perf += [(flip(c["Name"]), "conductor") for c in conductors]
    else:
        perf += [(flip(g["Name"]), "orchestra") for g in real_orch if g["Role"] == "Musical Group"]
        perf += [(flip(c["Name"]), "conductor") for c in conductors if c["Name"] not in HOUSE_COND and real_orch]
        credits += [flip(g["Name"]) for g in groups if g not in real_orch]
        credits += [f"conducted by {flip(c['Name'])}" for c in conductors if c["Name"] in HOUSE_COND or not real_orch]
    seen = set(); perf = [p for p in perf if not (p[0] in seen or seen.add(p[0]))]
    if not perf: why["no performer"] += 1; continue
    if len(perf) > 4: why["too many performers"] += 1; continue
    y = int(r["Date"][:4]) if re.match(r"\d{4}", r.get("Date") or "") else None
    if not y or y > 1925: why["date"] += 1; continue
    out.append({"id": "loc-" + r["Id"].rstrip("/").rsplit("-", 1)[-1], "title": t, "composers": composers, "performers": perf,
                "credits": credits, "year": y, "date": r["Date"], "genres": sorted(genres), "audio": a, "source": r["Url"],
                "label": r.get("Recording_label") or "Victor", "catalog": r.get("Recording_catalog_number"), "place": r.get("Location_text") or "",
                "description": (r.get("Description") or [""])[-1], "language": r.get("Language") or []})
json.dump(out, open("sources/loc-selected.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(out), "records kept; skipped:", dict(why))
