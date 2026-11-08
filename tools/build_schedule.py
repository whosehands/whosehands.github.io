"""Rebuild the daily schedule without changing any day that has already happened.
Usage: python3 tools/build_schedule.py PREVIOUS_CATALOG.json"""
import json, sys, random, datetime
CAT = "data/catalog.json"
cat = json.load(open(CAT, encoding="utf-8"))
prev = json.load(open(sys.argv[1], encoding="utf-8")) if len(sys.argv) > 1 else cat
y, m, d = map(int, prev["epoch"].split("-"))
today = (datetime.date.today() - datetime.date(y, m, d)).days
fixed = prev["schedule"][: max(0, today + 1)]              # past days and today never change
by = {r["id"]: r for r in cat["recordings"]}
fixed = [i for i in fixed if i in by]
rng = random.Random(1926 + len(fixed))
def weight(r):  # well-known performers come up more often
    return {"famous": 3, "known": 2}.get(r.get("performerFame"), 1) * (1.5 if r.get("composerFame") == "famous" else 1)
pools = {"roll": [], "record": []}
for r in cat["recordings"]:
    if r["id"] not in fixed: pools[r.get("kind", "roll")].append(r)
for k in pools:  # weighted shuffle
    pools[k].sort(key=lambda r: -rng.random() ** (1 / weight(r)))
order, turn = list(fixed), 0
while pools["roll"] or pools["record"]:
    k = "roll" if (turn % 2 == 0 and pools["roll"]) or not pools["record"] else "record"
    order.append(pools[k].pop(0)["id"]); turn += 1
for i in range(len(fixed) + 1, len(order)):           # avoid the same performer two days running
    if set(by[order[i]]["performers"]) & set(by[order[i - 1]]["performers"]):
        for j in range(i + 1, len(order)):
            if not set(by[order[j]]["performers"]) & set(by[order[i - 1]]["performers"]):
                order[i], order[j] = order[j], order[i]; break
cat["schedule"] = order; cat["epoch"] = prev["epoch"]
json.dump(cat, open(CAT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(order), "days scheduled;", len(fixed), "kept as they were")
