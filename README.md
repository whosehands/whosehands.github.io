# Whose Hands

A daily guessing game. Every day you hear a piano roll recorded by a pianist between 1905 and 1925, and you guess the pianist, the piece and the year.

Play it at https://whosehands.github.io

## Where the music comes from

- **Piano rolls:** MIDI files from the [Stanford University Piano Roll Archive (SUPRA)](https://supra.stanford.edu), by Zhengshan Shi and Craig Stuart Sapp, licensed [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). The files in `midi/` are unchanged copies and keep that license. Only rolls published in 1925 or earlier are used.
- **Piano sound:** Salamander Grand Piano by Alexander Holm, licensed [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) (`samples/`).
- **Playback:** [Tone.js](https://tonejs.github.io) and [@tonejs/midi](https://github.com/Tonejs/Midi), MIT license (`vendor/`).

This is a free, non-commercial fan project.

## How it works

`data/catalog.json` lists every roll with its pianist, piece, recording year and source. The `schedule` array sets which roll plays on which day, starting from `epoch`. New recordings are added to the end of `recordings` and `schedule`, so past days never change.

Found a wrong answer? [Open an issue](https://github.com/whosehands/whosehands.github.io/issues/new).
