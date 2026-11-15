# Whose Hands

A daily guessing game for historic recordings. Every day you hear a random moment from a piano roll or a 78 record made between 1900 and 1925, and you guess who's performing, the piece and the year. A Practice tab gives you as many extra puzzles as you like, and a Score tab shows a few bars of sheet music to name.

Play it at https://whosehands.github.io

## How a round works

- You guess the performers, the piece and the year together, in one form. The clip starts at 2 seconds. Right answers keep it as it is; each miss plays more (up to 24 seconds) and earns a hint. You choose whether each hint is about the performer, the piece or the year.
- The sooner you get each answer, the more it's worth: performers up to 5, piece up to 3, year up to 2 (within 2 years counts; a wrong year tells you "earlier" or "later").
- Naming only the right composer earns 1 point for the piece, but not after you've opened the hint that names the composer.
- Every puzzle plays a random part of the piece, so a recording can come back later with a different section.
- Clues work like quiz bowl: each kind (performer, piece, year) starts with obscure, specific facts and gets more obvious. Clues about what you already know are skipped.
- Pieces that belong to a published set (Chopin's Études, Op. 10; Brahms's Intermezzi, Op. 117): name the set first, then pick which piece from a second list. The right set alone is worth 2 points.
- After a round you can download the whole recording. Rolls are rendered in the browser on the same piano as the game (MP3 or lossless WAV), or as the original MIDI.

## Guess the Score

A few bars of a score; name the piece. Each miss shows more bars and a clue, and you can listen to the bars. Scores are Humdrum files engraved in the browser with [Verovio](https://www.verovio.org) (LGPL-3.0, `vendor/verovio-*`).

- Chopin: his first editions, encoded by The Fryderyk Chopin Institute ([humdrum-chopin-first-editions](https://github.com/pl-wnifc/humdrum-chopin-first-editions)), CC BY 4.0.
- Mozart and Haydn piano sonatas: encoded by Craig Stuart Sapp ([mozart-piano-sonatas](https://github.com/craigsapp/mozart-piano-sonatas), [haydn-piano-sonatas](https://github.com/craigsapp/haydn-piano-sonatas)), CC BY-NC-SA 4.0.

`tools/build_scores.py` picks one edition per piece, removes the titles (so the file doesn't give the answer away) and writes `scores/` and `data/scores.json`.

## Where the music comes from

- **Piano rolls:** MIDI files from the [Stanford University Piano Roll Archive (SUPRA)](https://supra.stanford.edu), by Zhengshan Shi and Craig Stuart Sapp, licensed [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). The files in `midi/` are unchanged copies and keep that license. Only rolls published in 1925 or earlier are used.
- **Records:** the [Library of Congress National Jukebox](https://www.loc.gov/collections/national-jukebox/), recordings that are in the US public domain.
- **Piece names:** composers' work lists from [Wikidata](https://www.wikidata.org) (CC0).
- **Piano sound:** Salamander Grand Piano V3 by Alexander Holm, licensed [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/): seven velocity layers, key-release and pedal noises (`piano/`, see `piano/README.md`). Played by `piano.js` with Web Audio.
- **Clues:** facts from [Wikidata](https://www.wikidata.org) (CC0), fetched monthly by `tools/fetch_clues.py`; `tools/build_clues.py` turns them into clues.
- **Code libraries:** [@tonejs/midi](https://github.com/Tonejs/Midi) (MIT), [lamejs](https://github.com/zhuker/lamejs) MP3 encoder (LGPL-3.0), [Verovio](https://www.verovio.org) (LGPL-3.0), all in `vendor/`.

This is a free, non-commercial fan project. Visits are counted with GoatCounter, which uses no cookies and stores no personal data.

## How the data is kept up to date

GitHub Actions in `.github/workflows/` download the source listings into `sources/` once a month. `data/catalog.json` lists every recording with its performers, piece, year and source. The `schedule` array sets which recording plays on which day, starting from `epoch`; new recordings are only ever added after today's position, so past days never change.

See what changed on the site's [What's new](https://whosehands.github.io/#changelog) page (`data/changelog.json`).

`tools/check_catalog.py` looks for duplicate answers (the same piece in two languages, a set next to its own pieces, near-identical titles). Fix them in `data/same-piece.json` (`{"name to drop": "name to keep"}`), `data/label-fixes.json` or `data/overrides.json`.

Found a wrong answer? [Open an issue](https://github.com/whosehands/whosehands.github.io/issues/new).
