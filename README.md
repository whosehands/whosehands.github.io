# Whose Hands

A daily guessing game for historic recordings. Every day you hear a random moment from a piano roll or a 78 record made between 1900 and 1925, and you guess who's performing, the piece and the year. A Practice tab gives you as many extra puzzles as you like.

Play it at https://whosehands.github.io

## How a round works

- You guess the performers, the piece and the year together, in one form. The clip starts at 2 seconds. Right answers keep it as it is; each miss plays more (up to 24 seconds) and earns a hint. You choose whether each hint is about the performer, the piece or the year.
- The sooner you get each answer, the more it's worth: performers up to 5, piece up to 3, year up to 2 (within 2 years counts; a wrong year tells you "earlier" or "later").
- Naming only the right composer earns 1 point for the piece, but not after you've opened the hint that names the composer.
- Every puzzle plays a random part of the piece, so a recording can come back later with a different section.

## Where the music comes from

- **Piano rolls:** MIDI files from the [Stanford University Piano Roll Archive (SUPRA)](https://supra.stanford.edu), by Zhengshan Shi and Craig Stuart Sapp, licensed [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). The files in `midi/` are unchanged copies and keep that license. Only rolls published in 1925 or earlier are used.
- **Records:** the [Library of Congress National Jukebox](https://www.loc.gov/collections/national-jukebox/), recordings that are in the US public domain.
- **Piece names:** composers' work lists from [Wikidata](https://www.wikidata.org) (CC0).
- **Piano sound:** Salamander Grand Piano by Alexander Holm, licensed [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) (`samples/`).
- **Playback:** [Tone.js](https://tonejs.github.io) and [@tonejs/midi](https://github.com/Tonejs/Midi), MIT license (`vendor/`).

This is a free, non-commercial fan project. Visits are counted with GoatCounter, which uses no cookies and stores no personal data.

## How the data is kept up to date

GitHub Actions in `.github/workflows/` download the source listings into `sources/` once a month. `data/catalog.json` lists every recording with its performers, piece, year and source. The `schedule` array sets which recording plays on which day, starting from `epoch`; new recordings are only ever added after today's position, so past days never change.

See what changed on the site's [What's new](https://whosehands.github.io/#changelog) page (`data/changelog.json`).

Found a wrong answer? [Open an issue](https://github.com/whosehands/whosehands.github.io/issues/new).
