"""Download the Library of Congress National Jukebox dataset (public-domain Victor recordings, 1900-1922).
Runs on GitHub Actions. Saves the dataset's own metadata and audio manifest into sources/."""
import urllib.request, sys, time
UA = {"User-Agent": "WhoseHands-bot (github.com/whosehands/whosehands.github.io)"}
for name in ("metadata.jsonl", "manifest.txt"):
    for i in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request("https://data.labs.loc.gov/jukebox/" + name, headers=UA), timeout=300) as r:
                open("sources/loc-jukebox-" + name, "wb").write(r.read())
            print("saved", name, flush=True); break
        except Exception as e:
            print("retry", i, e, flush=True); time.sleep(30 * (i + 1))
    else:
        sys.exit("could not download " + name)
