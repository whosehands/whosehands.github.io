/* Whose Hands — a daily guessing game for historic recordings.
   Rolls: Stanford University Piano Roll Archive (CC BY-NC-SA 4.0).
   Records: Library of Congress National Jukebox (public domain in the US).
   Piano sound: Salamander Grand Piano by Alexander Holm (CC BY 3.0). Playback: Tone.js (MIT). */
(function () {
  "use strict";
  const SNIPS = [2, 4, 7, 11, 16, 24];          // clip length after 0..5 misses
  const MAX_MISSES = SNIPS.length;
  const REPO = "whosehands/whosehands.github.io";
  const YEAR_MIN = 1900, YEAR_MAX = 1930;
  const DECOYS = ["Sergei Rachmaninoff", "Leopold Godowsky", "Moriz Rosenthal", "Alfred Cortot", "Ignaz Friedman", "Percy Grainger",
    "Harold Bauer", "Ossip Gabrilowitsch", "Franz Liszt", "Claude Debussy", "Edvard Grieg", "Gustav Mahler", "Alexander Scriabin",
    "Enrique Granados", "Maurice Ravel", "Leopold Stokowski", "Myra Hess", "Benno Moiseiwitsch", "Arthur Rubinstein", "Vladimir Horowitz"];
  const app = document.getElementById("app");
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const norm = s => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9#♯♭]+/g, " ").trim();
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  };

  let CAT, BY_ID, DAY;            // catalog, recordings by id, today's day number (0 = No. 1)
  let MODE, P, S;                 // "daily" | "practice", current recording, current game state
  let DRAW_LIMIT = SNIPS[0];      // seconds of the piece the player is allowed to see on the roll

  /* ---------- helpers ---------- */
  function dayIndex(epoch) {
    const [y, m, d] = epoch.split("-").map(Number);
    const e = new Date(y, m - 1, d), n = new Date();
    return Math.round((new Date(n.getFullYear(), n.getMonth(), n.getDate()) - e) / 86400000);
  }
  function seeded(n) {               // deterministic 0..1 from an integer (mulberry32)
    let t = (n + 0x6D2B79F5) | 0;
    t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  const surname = n => norm(n).split(" ").pop();
  function nameMatches(guess, answer) {
    const g = norm(guess); if (!g) return false;
    if (g === norm(answer)) return true;
    const sn = surname(answer);
    return g === sn && !CAT.allPerformers.some(p => surname(p) === sn && norm(p) !== norm(answer));
  }
  const composerOf = s => norm(String(s).split(" – ")[0]);
  const roleOf = i => (P.roles && P.roles[i]) || "piano";
  const ROLE_NAMES = { piano: "Pianist", violin: "Violinist", cello: "Cellist", flute: "Flutist", harp: "Harpist", organ: "Organist",
    cornet: "Cornetist", clarinet: "Clarinetist", xylophone: "Xylophonist", trombone: "Trombonist", trumpet: "Trumpeter", banjo: "Banjo player", vocalist: "Singer" };
  function roleLabel(i) {
    const r = roleOf(i), base = ROLE_NAMES[r] || r.charAt(0).toUpperCase() + r.slice(1);
    const same = (P.roles || P.performers.map(() => "piano")).filter(x => x === r).length;
    if (same > 1) { const n = (P.roles || P.performers.map(() => "piano")).slice(0, i + 1).filter(x => x === r).length; return base + " " + n; }
    return base;
  }

  /* ---------- scoring (based on misses before the answer was found) ---------- */
  const namePts = a => (a ? [0, 5, 4, 3, 2, 1, 1, 1][a] : 0);
  const piecePts = a => (a ? (a <= 2 ? 3 : a <= 4 ? 2 : 1) : 0);
  const yearPtsAt = a => (a ? (a <= 2 ? 2 : a <= 4 ? 1.5 : 1) : 0);
  const YEAR_TOL = 2;                                   // a year guess within 2 years of the recording counts
  const yearOff = y => (y < P.yearMin ? P.yearMin - y : y > P.yearMax ? y - P.yearMax : 0);
  const yearPts = () => yearPtsAt(S.yearAt);
  const namesScore = () => S.nameAt.reduce((s, a) => s + namePts(a) / P.performers.length, 0);
  const pieceScore = () => (S.pieceAt ? piecePts(S.pieceAt) : S.composerAt ? 1 : 0);
  const total = () => Math.round((namesScore() + pieceScore() + yearPts()) * 10) / 10;
  const allSolved = () => allNames() && !!S.pieceAt && !!S.yearAt;
  const allNames = () => S.nameAt.every(Boolean);

  /* ---------- audio ---------- */
  const Player = {
    forId: null, notes: null, el: null, start: 0, sampler: null, samplerLoading: null, loading: null, playing: false, raf: 0,
    reset() { this.stop(); this.forId = null; this.notes = null; this.loading = null; if (this.el) { this.el.src = ""; this.el = null; } this.start = 0; },
    loadSampler() {
      if (this.samplerLoading) return this.samplerLoading;
      this.samplerLoading = new Promise((res, rej) => {
        const urls = {}, names = { A: "A", C: "C", Ds: "D#", Fs: "F#" };
        for (let o = 0; o <= 8; o++) for (const k of Object.keys(names)) {
          if ((o === 0 && k !== "A") || (o === 8 && k !== "C")) continue;
          urls[names[k] + o] = k + o + ".mp3";
        }
        this.sampler = new Tone.Sampler({ urls, baseUrl: "samples/", release: 1, onload: res, onerror: rej }).toDestination();
      });
      return this.samplerLoading;
    },
    load() {                                   // prepare the current recording and pick the segment
      if (this.forId === P.id && this.loading) return this.loading;
      this.reset(); this.forId = P.id;
      this.loading = P.kind === "record" ? this.loadRecord() : this.loadRoll();
      return this.loading;
    },
    async loadRoll() {
      const midi = new Midi(await (await fetch(P.midi)).arrayBuffer());
      const pedal = [], soft = [];
      midi.tracks.forEach(t => {
        (t.controlChanges[64] || []).forEach(c => pedal.push([c.time, c.value >= 0.5]));
        (t.controlChanges[67] || []).forEach(c => soft.push([c.time, c.value >= 0.5]));
      });
      pedal.sort((a, b) => a[0] - b[0]); soft.sort((a, b) => a[0] - b[0]);
      const stateAt = (list, t) => { let s = false; for (const [ti, v] of list) { if (ti > t) break; s = v; } return s; };
      const nextUp = t => { for (const [ti, v] of pedal) if (ti > t && !v) return ti; return t + 4; };
      const notes = [];
      midi.tracks.forEach(t => t.notes.forEach(n => {
        let end = n.time + n.duration;
        if (stateAt(pedal, end)) end = Math.max(end, nextUp(end));
        let v = Math.min(1, n.velocity * 1.55);
        if (stateAt(soft, n.time)) v *= 0.8;
        notes.push({ name: n.name, midi: n.midi, time: n.time, dur: Math.max(0.05, end - n.time), vel: v });
      }));
      notes.sort((a, b) => a.time - b.time);
      this.notes = notes;
      if (!notes.length) return;
      const first = notes[0].time, last = notes[notes.length - 1].time;
      const latest = Math.max(first, last - SNIPS[SNIPS.length - 1] - 8);
      const target = first + S.frac * (latest - first);
      const onset = notes.find(n => n.time >= target - 0.01);       // start on a real note
      this.start = onset ? onset.time : first;
    },
    async loadRecord() {
      const a = new window.Audio(); a.preload = "auto"; a.src = P.audio; this.el = a;
      await new Promise((res, rej) => {
        a.addEventListener("loadedmetadata", res, { once: true });
        a.addEventListener("error", () => rej(new Error("audio")), { once: true });
      });
      const lead = 4, tail = SNIPS[SNIPS.length - 1] + 8;              // skip the surface noise at the start
      const span = Math.max(0, (a.duration || 0) - lead - tail);
      this.start = lead + S.frac * span;
    },
    async play(secs, onTick, onEnd) {
      const started = P.kind === "record" ? null : Tone.start();      // must begin inside the click
      await this.load();
      this.stop();
      if (P.kind === "record") {
        const a = this.el; a.currentTime = this.start; await a.play();
        this.playing = true;
        this.timer = setTimeout(() => this.stop(onEnd), (secs + 0.3) * 1000);   // runs even when the tab is in the background
        const loop = () => {
          if (!this.playing) return;
          const el = a.currentTime - this.start;
          onTick && onTick(Math.min(el, secs));
          if (el >= secs || a.ended) { this.stop(onEnd); return; }
          this.raf = requestAnimationFrame(loop);
        };
        return loop();
      }
      await Promise.all([started, this.loadSampler()]);
      const T = Tone.Transport, t0 = this.start;
      this.notes.forEach(n => {
        const off = n.time - t0;
        if (off < -0.001 || off > secs) return;
        T.schedule(time => this.sampler.triggerAttackRelease(n.name, Math.min(n.dur, secs - off + 0.6), time, n.vel), off);
      });
      T.start("+0.05");
      this.playing = true;
      this.timer = setTimeout(() => this.stop(onEnd), (secs + 0.9) * 1000);   // runs even when the tab is in the background
      const loop = () => { if (!this.playing) return; onTick && onTick(Math.min(T.seconds, secs)); this.raf = requestAnimationFrame(loop); };
      loop();
    },
    stop(onEnd) {
      clearTimeout(this.timer);
      if (this.el) this.el.pause();
      if (window.Tone) { Tone.Transport.stop(); Tone.Transport.cancel(0); }
      if (this.sampler) this.sampler.releaseAll();
      cancelAnimationFrame(this.raf);
      const was = this.playing; this.playing = false;
      if (was && onEnd) onEnd();
    }
  };

  /* ---------- drawing ---------- */
  function draw(canvas, at) {
    const dpr = window.devicePixelRatio || 1, w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr)) { canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); }
    const g = canvas.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const css = getComputedStyle(document.documentElement), roll = css.getPropertyValue("--roll").trim(), hole = css.getPropertyValue("--hole").trim();
    g.fillStyle = roll; g.fillRect(0, 0, w, h);
    if (P.kind === "record") {
      const cx = w / 2, cy = h / 2, R = h * 0.46;
      g.fillStyle = "#121214"; g.beginPath(); g.arc(cx, cy, R, 0, Math.PI * 2); g.fill();
      g.strokeStyle = "rgba(255,255,255,.07)"; g.lineWidth = 1;
      for (let r = R * 0.42; r < R - 2; r += 2.5) { g.beginPath(); g.arc(cx, cy, r, 0, Math.PI * 2); g.stroke(); }
      const ang = (at || 0) * 78 / 60 * Math.PI * 2;
      g.strokeStyle = "rgba(255,255,255,.18)"; g.lineWidth = R * 0.5; g.beginPath(); g.arc(cx, cy, R * 0.7, ang, ang + 0.35); g.stroke();
      g.fillStyle = roll; g.beginPath(); g.arc(cx, cy, R * 0.36, 0, Math.PI * 2); g.fill();
      g.fillStyle = hole; g.beginPath(); g.arc(cx, cy, 3, 0, Math.PI * 2); g.fill();
      return;
    }
    if (!Player.notes || Player.forId !== P.id) return;
    g.fillStyle = hole;
    const span = 3.2, px = h / span, now = Player.start + (at || 0);
    for (const n of Player.notes) {
      if (n.time > now + span || n.time > Player.start + DRAW_LIMIT + 0.02) break;   // never show notes past the unlocked clip
      const len = Math.min(n.dur, 1.2);
      if (n.time + len < now - 0.2) continue;
      const x = ((n.midi - 21) / 88) * (w - 16) + 8, y = h - (n.time - now) * px - 18;
      g.fillRect(x, y - len * px * 0.35, Math.max(2, w / 160), Math.max(3, len * px * 0.35));
    }
    g.fillStyle = "rgba(255,255,255,.35)"; g.fillRect(0, h - 18, w, 1);
  }

  /* ---------- game state ---------- */
  function freshState(id, frac) {
    return { id, frac, guesses: [], misses: 0, nameAt: BY_ID[id].performers.map(() => 0), pieceAt: 0, composerAt: 0, year: null, yearAt: 0, hints: [], done: false };
  }
  const stateKey = () => (MODE === "daily" ? "wh3-day-" + DAY : "wh3-practice");
  const save = () => store.set(stateKey(), S);
  const FAME = [["any", "Any"], ["famous", "Famous"], ["known", "Well known"], ["obscure", "Obscure"]];
  function defaultFilters() { return { kinds: { roll: true, record: true }, genres: {}, yearFrom: YEAR_MIN, yearTo: YEAR_MAX, composer: "any", performer: "any" }; }
  let FILTERS = null;
  const filters = () => (FILTERS = FILTERS || Object.assign(defaultFilters(), store.get("wh3-filters", {})));
  function passes(r, f) {
    if (f.kinds[r.kind || "roll"] === false) return false;
    if (f.genres[r.genre] === false) return false;
    if (r.yearMax < f.yearFrom || r.yearMin > f.yearTo) return false;
    if (f.composer !== "any" && (r.composerFame || "obscure") !== f.composer) return false;
    if (f.performer !== "any" && (r.performerFame || (r.famous ? "famous" : "obscure")) !== f.performer) return false;
    return true;
  }
  function practicePool() {
    const soon = new Set();
    for (let d = DAY; d < DAY + 30; d++) soon.add(CAT.schedule[d % CAT.schedule.length]);   // keep the next month's dailies unspoiled
    const f = filters();
    return CAT.recordings.filter(r => !soon.has(r.id) && passes(r, f));
  }
  function filtersHTML() {
    const f = filters(), n = practicePool().length;
    const genres = [...new Set(CAT.recordings.map(r => r.genre).filter(Boolean))].sort();
    const kinds = [...new Set(CAT.recordings.map(r => r.kind || "roll"))];
    const years = []; for (let y = YEAR_MIN; y <= YEAR_MAX; y++) years.push(y);
    const sel = (id, val, opts) => `<select id="${id}">${opts.map(([v, l]) => `<option value="${v}" ${String(v) === String(val) ? "selected" : ""}>${l}</option>`).join("")}</select>`;
    const hasFame = CAT.recordings.some(r => r.composerFame);
    return `<details class="panel filters" ${store.get("wh3-filters-open", false) ? "open" : ""}>
      <summary><span class="label">Filters</span><span class="pts" id="fcount">${n} recording${n === 1 ? "" : "s"} match</span></summary>
      ${kinds.length > 1 ? `<fieldset><legend class="label">Format</legend>${kinds.map(k => `<label class="check"><input type="checkbox" data-kind="${k}" ${f.kinds[k] !== false ? "checked" : ""}> ${k === "roll" ? "Piano rolls" : "78 records"}</label>`).join("")}</fieldset>` : ""}
      <fieldset><legend class="label">Genre</legend>${genres.map(g => `<label class="check"><input type="checkbox" data-genre="${esc(g)}" ${f.genres[g] !== false ? "checked" : ""}> ${esc(g)}</label>`).join("")}</fieldset>
      <fieldset class="fyears"><legend class="label">Recorded</legend>${sel("f-from", f.yearFrom, years.map(y => [y, y]))}<span>to</span>${sel("f-to", f.yearTo, years.map(y => [y, y]))}</fieldset>
      ${hasFame ? `<fieldset class="fyears"><legend class="label">Composer</legend>${sel("f-comp", f.composer, FAME)}</fieldset>` : ""}
      <fieldset class="fyears"><legend class="label">${CAT.recordings.some(r => r.kind === "record") ? "Performer" : "Pianist"}</legend>${sel("f-perf", f.performer, hasFame ? FAME : FAME.filter(x => x[0] !== "known"))}</fieldset>
      <div class="controls"><button class="btn primary" id="fapply" ${n ? "" : "disabled"}>New puzzle with these filters</button><button class="btn" id="freset">Reset</button></div>
    </details>`;
  }
  function wireFilters() {
    const box = document.querySelector(".filters"); if (!box) return;
    box.addEventListener("toggle", () => store.set("wh3-filters-open", box.open));
    const f = filters();
    const update = () => {
      box.querySelectorAll("[data-kind]").forEach(el => (f.kinds[el.dataset.kind] = el.checked));
      box.querySelectorAll("[data-genre]").forEach(el => (f.genres[el.dataset.genre] = el.checked));
      f.yearFrom = +document.getElementById("f-from").value; f.yearTo = +document.getElementById("f-to").value;
      if (f.yearFrom > f.yearTo) [f.yearFrom, f.yearTo] = [f.yearTo, f.yearFrom];
      const c = document.getElementById("f-comp"); if (c) f.composer = c.value;
      f.performer = document.getElementById("f-perf").value;
      store.set("wh3-filters", f);
      const n = practicePool().length;
      document.getElementById("fcount").textContent = `${n} recording${n === 1 ? "" : "s"} match`;
      document.getElementById("fapply").disabled = !n;
    };
    box.querySelectorAll("input, select").forEach(el => el.addEventListener("change", update));
    document.getElementById("fapply").onclick = () => { Player.reset(); newPractice(); render(); Player.load().then(() => draw(document.getElementById("roll"), 0)).catch(() => {}); };
    document.getElementById("freset").onclick = () => { FILTERS = defaultFilters(); store.set("wh3-filters", FILTERS); render(); };
  }
  function newPractice() {
    let pool = practicePool();
    if (!pool.length) pool = CAT.recordings;
    const r = pool[Math.floor(Math.random() * pool.length)];
    S = freshState(r.id, Math.random()); P = r; save();
  }
  function setMode(mode) {
    Player.reset();
    MODE = mode;
    if (mode === "daily") {
      P = BY_ID[CAT.schedule[DAY % CAT.schedule.length]];
      const s = store.get(stateKey(), null);
      S = s && s.id === P.id && s.nameAt ? s : freshState(P.id, seeded(DAY * 7919 + 17));
      if (S.yearAt === undefined) S.yearAt = S.year != null && yearOff(S.year) <= YEAR_TOL ? Math.max(1, S.misses) : 0;   // games saved before the year joined the guesses
    } else {
      const s = store.get(stateKey(), null);
      if (s && BY_ID[s.id] && s.nameAt) { S = s; P = BY_ID[s.id]; if (S.yearAt === undefined) S.yearAt = S.year != null && yearOff(S.year) <= YEAR_TOL ? Math.max(1, S.misses) : 0; } else newPractice();
    }
    render();
    Player.load().then(() => { const c = document.getElementById("roll"); if (c) draw(c, 0); }).catch(() => {});
  }
  function recordStats() {
    const key = MODE === "daily" ? "wh2-stats" : "wh3-practice-stats";
    const st = store.get(key, { played: 0, total: 0, best: 0, days: {} });
    const tag = MODE === "daily" ? DAY : S.id + ":" + S.frac;
    if (st.days[tag] !== undefined) return;
    const pts = total(); st.days[tag] = pts; st.played++; st.total += pts; st.best = Math.max(st.best, pts);
    store.set(key, st);
  }

  /* ---------- hints: each miss earns one, and the player picks the kind ---------- */
  const HINT_KINDS = [["who", "Performer"], ["what", "Piece"], ["when", "Year"]];
  const FORMS = /^(ballade|nocturne|waltz|valse|[ée]tude|pr[ée]lude|sonata|sonatina|mazurka|polonaise|impromptu|rhapsod\w*|intermezzo|scherzo|fantas\w*|march|marche|overture|ouverture|symphony|concerto|serenade|s[ée]r[ée]nade|barcarolle|berceuse|rondo|variations|minuet|menuet|gavotte|humoresque|romance|caprice|capriccio|toccata|fugue|suite|polka|tarantell\w*|novelette|arabesque|[ée]l[ée]g\w*|consolation|bagatelle|danse|dance|nachtst\w*|song|chanson|lied|ave maria)\b/i;
  const born = s => +((String(s || "").match(/^(\d{4})/) || [])[1] || 0);
  const died = s => +((String(s || "").match(/-(\d{4})$/) || [])[1] || 0);
  const lifeText = d => (died(d) ? `lived ${born(d)}–${died(d)}` : `was born in ${born(d)}`);
  const aAn = t => (/^[AEIOU]/i.test(t) ? "an " : "a ") + t;
  const whoOf = i => (P.kind === "record" ? `The ${roleLabel(i).toLowerCase()}` : "The pianist");
  function hintLadder(kind, i) {           // from vague to specific
    const out = [], y = P.yearMin;
    if (kind === "who") {
      const name = P.performers[i], who = whoOf(i), d = (P.performerDates || {})[name], cnt = CAT.countBy[name] || 1;
      const about = (P.performerAbout || {})[name];
      if (about) out.push(`${who} was ${aAn(about)}`);
      if (born(d)) out.push(`${who} ${lifeText(d)}`);
      out.push(cnt > 1 ? `${who} is on ${cnt} recordings in this game` : `This is ${who.toLowerCase()}'s only recording in this game`);
      const words = name.split(/\s+/).filter(Boolean);
      if (roleOf(i) === "orchestra" || /orchestra|band|quartet|trio|chorus|ensemble|company|choir/i.test(name)) {
        out.push(`The name has ${words.length} word${words.length > 1 ? "s" : ""}`);
        out.push(`The name starts with “${name[0]}”`);
      } else {
        const sn = words[words.length - 1].replace(/[^\p{L}]/gu, "");
        out.push(`${who}'s last name has ${sn.length} letters`);
        out.push(`${who}'s initials are ${words.filter(w => /^\p{Lu}/u.test(w)).map(w => w[0] + ".").join(" ")}`);
      }
    } else if (kind === "what") {
      const g = { "Opera & stage": "It's from an opera or other stage work", "Art songs": "It's an art song", "Orchestral": "It's orchestral music", "Piano music": "It was written for piano" }[P.genre];
      if (g) out.push(g + (P.kind !== "record" && P.genre !== "Piano music" ? ", arranged for piano" : ""));
      if (P.composerAbout) out.push(`The composer was ${aAn(P.composerAbout)}`);
      if (born(P.composerDates)) out.push(`The composer ${lifeText(P.composerDates)}`);
      out.push({ text: `Composer: ${P.composer}`, reveals: "composer" });
      const title = P.piece.split(" – ").slice(1).join(" – ") || P.piece, form = title.match(FORMS), key = title.match(/\bin ([A-G](?:[-‐ ]?(?:flat|sharp)|♭|♯)? (?:major|minor))/i);
      if (form) out.push(`Kind of piece: ${form[1].charAt(0).toUpperCase() + form[1].slice(1).toLowerCase()}`);
      if (key) out.push(`Key: ${key[1].replace("♭", "-flat").replace("♯", "-sharp")}`);
      if (!form) out.push(`The title starts with “${title.replace(/^[^\p{L}]+/u, "")[0]}”`);
    } else {
      const dec = n => Math.floor(n / 10) * 10, range = `Recorded between ${P.yearMin} and ${P.yearMax}`;
      out.push(dec(P.yearMin) === dec(P.yearMax) ? `Recorded in the ${dec(y)}s` : range);
      const cb = born(P.composerDates), cd = died(P.composerDates);
      if (cd && cd < y) out.push(`The composer had died ${y - cd} year${y - cd > 1 ? "s" : ""} before it was recorded`);
      else if (cd === y) out.push("The composer died the year it was recorded");
      else if (cb) out.push(`The composer was alive, about ${y - cb} years old`);
      const pi = P.performers.findIndex(n => born((P.performerDates || {})[n]));
      if (pi >= 0) out.push(`${whoOf(pi)} was about ${y - born(P.performerDates[P.performers[pi]])} years old`);
      const lo = y - (y % 5);
      if (P.yearMax <= lo + 4) out.push(`Recorded between ${lo} and ${lo + 4}`);
      else if (dec(P.yearMin) === dec(P.yearMax)) out.push(range);
    }
    return out.map(h => (typeof h === "string" ? { text: h } : h));
  }
  function takenHints() {                  // the hints opened so far, in order
    const seen = {};
    return (S.hints || []).map(h => {
      const key = h.k + (h.i ?? ""), n = (seen[key] = (seen[key] ?? -1) + 1);
      const item = hintLadder(h.k, h.i || 0)[n];
      return item && { ...item, kind: HINT_KINDS.find(x => x[0] === h.k)[1] };
    }).filter(Boolean);
  }
  const composerRevealed = () => takenHints().some(h => h.reveals === "composer");
  function nextHint(kind) {                // what a hint of this kind would target, or null if there's nothing left to give
    const i = kind === "who" ? S.nameAt.findIndex(a => !a) : 0;
    if (kind === "who" ? i < 0 : kind === "what" ? S.pieceAt : S.yearAt) return null;
    const used = (S.hints || []).filter(h => h.k === kind && (h.i || 0) === i).length;
    return used < hintLadder(kind, i).length ? { k: kind, i } : null;
  }

  /* ---------- search-as-you-type ---------- */
  const index = list => list.map(t => ({ t, n: " " + norm(t) + " " }));
  function suggest(input, idx) {
    input.setAttribute("autocomplete", "off"); input.setAttribute("role", "combobox"); input.setAttribute("aria-expanded", "false");
    const box = document.createElement("ul"); box.className = "suggest"; box.setAttribute("role", "listbox"); box.hidden = true;
    input.insertAdjacentElement("afterend", box);
    let items = [], sel = -1;
    const show = () => {
      const q = norm(input.value);
      if (!q) { box.hidden = true; input.setAttribute("aria-expanded", "false"); return; }
      const toks = q.split(" ");
      const hits = [];
      for (const o of idx) {
        let ok = true, score = 0;
        for (const t of toks) { const at = o.n.indexOf(t); if (at < 0) { ok = false; break; } if (o.n[at - 1] === " ") score += 2; }
        if (ok) hits.push([score * 1000 - o.t.length, o.t]);
      }
      hits.sort((a, b) => b[0] - a[0]);
      items = hits.slice(0, 8).map(h => h[1]); sel = -1;
      if (items.some(t => norm(t) === q)) { box.hidden = true; input.setAttribute("aria-expanded", "false"); return; }   // already a full answer
      if (!items.length) { box.hidden = true; input.setAttribute("aria-expanded", "false"); return; }
      box.innerHTML = items.map((t, i) => `<li role="option" data-i="${i}">${esc(t)}</li>`).join("");
      box.hidden = false; input.setAttribute("aria-expanded", "true");
    };
    const pick = i => { if (items[i] != null) input.value = items[i]; box.hidden = true; input.setAttribute("aria-expanded", "false"); };
    const mark = () => [...box.children].forEach((li, i) => li.classList.toggle("on", i === sel));
    input.addEventListener("input", show);
    input.addEventListener("focus", () => { if (input.value) show(); });
    input.addEventListener("blur", () => setTimeout(() => { box.hidden = true; }, 120));
    input.addEventListener("keydown", e => {
      if (box.hidden || !items.length) return;
      if (e.key === "ArrowDown") { sel = Math.min(items.length - 1, sel + 1); mark(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { sel = Math.max(0, sel - 1); mark(); e.preventDefault(); }
      else if (e.key === "Enter" && sel >= 0) { pick(sel); e.preventDefault(); }
      else if (e.key === "Escape") { box.hidden = true; }
    });
    box.addEventListener("mousedown", e => { const li = e.target.closest("li[data-i]"); if (li) { pick(+li.dataset.i); e.preventDefault(); } });
  }

  /* ---------- changelog ---------- */
  function renderChangelog() {
    Player.stop();
    app.innerHTML = `<header><h1>Whose <em>Hands</em></h1><span class="meta">What's new</span></header>
    <nav class="tabs" aria-label="Mode"><a href="#">Daily</a><a href="#practice">Practice</a></nav>
    <section class="panel changelog"><h2>What's new</h2><p class="how" id="cl-loading">Loading…</p></section>`;
    fetch("data/changelog.json").then(r => r.json()).then(list => {
      const fmt = d => new Date(d + "T12:00:00").toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" });
      document.querySelector(".changelog").innerHTML = `<h2>What's new</h2>` + list.map(e => `<div class="entry"><div class="row"><h3>${esc(e.title || "Update")}</h3><span class="pts">${esc(fmt(e.date))}</span></div><ul>${e.items.map(i => `<li>${esc(i)}</li>`).join("")}</ul></div>`).join("");
    }).catch(() => { document.getElementById("cl-loading").textContent = "The changelog didn't load. Reload the page to try again."; });
  }

  /* ---------- render ---------- */
  function render() {
    const daily = MODE === "daily";
    const step = S.done ? SNIPS.length - 1 : Math.min(S.misses, SNIPS.length - 1);
    const secs = SNIPS[step];
    const hs = takenHints(), toOpen = S.done ? 0 : S.misses - (S.hints || []).length;
    const dateStr = new Date().toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
    const tag = daily ? "NO. " + (DAY + 1) : "PRACTICE";
    const fresh = !S.guesses.length && !S.done;

    app.innerHTML = `
    <header><h1>Whose <em>Hands</em></h1><span class="meta">${daily ? `No. ${DAY + 1} · ${esc(dateStr)}` : "Practice"}</span></header>
    <nav class="tabs" aria-label="Mode">
      <a href="#" class="${daily ? "on" : ""}" ${daily ? 'aria-current="page"' : ""}>Daily</a>
      <a href="#practice" class="${daily ? "" : "on"}" ${daily ? "" : 'aria-current="page"'}>Practice</a>
    </nav>
    ${fresh ? `<p class="how">${P.kind === "record"
      ? "This is a 78 record. Guess everyone featured on it, the piece, and the year it was recorded."
      : "A pianist recorded this on a piano roll. You hear their exact notes, pedaling and timing on a modern piano. Guess who, what, and the year it was recorded."}
      You hear a random part of the piece. Guess all three together: the sooner you get each one, the more it's worth. Right answers keep the clip as it is; each miss plays more and earns a hint, and you choose what it's about.</p>` : ""}
    ${!daily ? filtersHTML() + `<div class="controls"><button class="btn" id="newp">${S.done ? "Next puzzle" : "Skip to a new puzzle"}</button></div>` : ""}

    <section class="player" aria-label="Recording">
      <div class="rollbox"><canvas id="roll" aria-hidden="true"></canvas><span class="tag">${tag}</span><span class="status" id="status"></span></div>
      <div class="controls"><button class="btn primary" id="play">▶ Play ${secs}s</button><button class="btn" id="stop">Stop</button></div>
      <div><div class="bar">${SNIPS.map((v, i) => `<span class="${i <= step ? "open" : ""}" style="flex:${v - (i ? SNIPS[i - 1] : 0)}"><i></i></span>`).join("")}</div>
      <div class="legend"><span>0s</span><span>${SNIPS[SNIPS.length - 1]}s</span></div></div>
    </section>

    <section class="panel">
      <div class="row"><h2>${P.kind === "record" ? "Who's on it, what, and when?" : "Who's playing, what, and when?"}</h2><span class="pts">${S.misses}/${MAX_MISSES} misses</span></div>
      ${S.done ? "" : `<form id="guess" autocomplete="off">
        ${P.performers.map((p, i) => `<div class="field ${S.nameAt[i] ? "solved" : ""}"><div class="row"><label class="label" for="g-p${i}">${esc(roleLabel(i))}</label>${S.nameAt[i] ? `<span class="chip">✓</span>` : `<span class="pts">up to ${Math.round(50 / P.performers.length) / 10} pts</span>`}</div>
          <input type="text" id="g-p${i}" placeholder="${roleOf(i) === "orchestra" ? "Start typing an orchestra" : "Start typing a name"}" ${S.nameAt[i] ? `value="${esc(p)}" disabled` : ""}></div>`).join("")}
        <div class="field ${S.pieceAt ? "solved" : ""}"><div class="row"><label class="label" for="g-piece">Piece</label>${S.pieceAt ? `<span class="chip">✓</span>` : S.composerAt ? `<span class="chip part">Composer ✓</span>` : `<span class="pts">up to 3 pts${composerRevealed() ? "" : " · right composer 1"}</span>`}</div>
          <input type="text" id="g-piece" placeholder="Start typing a composer or title" ${S.pieceAt ? `value="${esc(P.piece)}" disabled` : ""}></div>
        <div class="field year ${S.yearAt ? "solved" : ""}"><div class="row"><label class="label" for="year">Year recorded</label>${S.yearAt ? `<span class="chip">✓</span>` : `<span class="pts">up to 2 pts · within ${YEAR_TOL} years</span>`}</div>
          <div class="row"><span class="val" id="yv">${S.year ?? "—"}</span>${!S.yearAt && S.year != null ? `<span class="pts" id="ydir">${S.year < P.yearMin ? "Later than " + S.year : "Earlier than " + S.year}</span>` : ""}</div>
          <input type="range" id="year" min="${YEAR_MIN}" max="${YEAR_MAX}" step="1" value="${S.year ?? Math.round((YEAR_MIN + YEAR_MAX) / 2)}" ${S.yearAt ? "disabled" : ""} aria-label="Year recorded"></div>
        <div class="controls"><button class="btn primary" type="submit">Guess</button><button class="btn" type="button" id="skip">Skip, play more</button></div>
      </form>`}
      ${hs.length || toOpen > 0 ? `<div class="hintbox"><div class="label">Hints</div>
        ${hs.length ? `<ul class="hints">${hs.map(h => `<li><span class="kind">${h.kind}</span> ${esc(h.text)}</li>`).join("")}</ul>` : ""}
        ${toOpen > 0 ? `<div class="hintpick"><span class="pts">${toOpen === 1 ? "You have a hint. What should it be about?" : `You have ${toOpen} hints. What should the next one be about?`}</span>
          <div class="controls">${HINT_KINDS.map(([k, label]) => `<button class="btn small" type="button" data-hint="${k}" ${nextHint(k) ? "" : "disabled"}>${label}</button>`).join("")}</div></div>` : ""}</div>` : ""}
      ${S.guesses.length ? `<ul class="tries">${S.guesses.map((t, i) => `<li><span class="n">${t.miss ? "✕" : "✓"}</span><span class="g">${t.p.map(x => `<span class="${x.ok ? "ok" : "no"}">${esc(x.g || "—")}</span>`).join(" · ")}<br><span class="${t.piece.ok ? "ok" : t.piece.comp ? "part" : "no"}">${esc(t.piece.g || "—")}</span>${t.y ? ` · <span class="${t.y.ok ? "ok" : "no"}">${t.y.g}</span>` : ""}</span></li>`).join("")}</ul>` : ""}
    </section>

    ${S.done ? resultHTML() : ""}

    <footer>
      <span>${daily ? "A new recording every day at midnight." : "Practice puzzles are random and don't count toward your daily stats."} Rolls from the <a href="https://supra.stanford.edu" target="_blank" rel="noopener">Stanford University Piano Roll Archive</a> (CC BY-NC-SA 4.0). Records from the <a href="https://www.loc.gov/collections/national-jukebox/" target="_blank" rel="noopener">Library of Congress National Jukebox</a> (public domain). Piano sound: Salamander Grand Piano by Alexander Holm (CC BY 3.0). Played with Tone.js.</span>
      <span><a href="#changelog">What's new</a> · Something wrong with an answer? <a href="https://github.com/${REPO}/issues/new?title=${encodeURIComponent("Problem with " + (daily ? "No. " + (DAY + 1) : "a practice puzzle"))}&body=${encodeURIComponent("Recording id: " + P.id + "\nWhat's wrong:\n")}" target="_blank" rel="noopener">Report it</a>.</span>
    </footer>
`;

    P.performers.forEach((_, i) => { const el = document.getElementById("g-p" + i); if (el && !el.disabled) suggest(el, CAT.nameIndex); });
    const pin = document.getElementById("g-piece"); if (pin && !pin.disabled) suggest(pin, CAT.pieceIndex);
    const canvas = document.getElementById("roll"), status = document.getElementById("status");
    DRAW_LIMIT = secs;
    draw(canvas, 0);
    const bars = [...app.querySelectorAll(".bar span i")];
    const tick = el => {
      draw(canvas, el);
      let acc = 0; bars.forEach((b, i) => { const len = SNIPS[i] - (i ? SNIPS[i - 1] : 0); b.style.width = Math.max(0, Math.min(1, (el - acc) / len)) * 100 + "%"; acc += len; });
    };
    document.getElementById("play").onclick = async () => {
      status.textContent = Player.forId === P.id && (Player.notes || Player.el) && Player.samplerLoading ? "PLAYING" : "LOADING…";
      try { await Player.play(secs, tick, () => { status.textContent = ""; }); status.textContent = "PLAYING"; }
      catch (e) { status.textContent = "COULDN'T LOAD AUDIO"; console.error(e); }
    };
    document.getElementById("stop").onclick = () => { Player.stop(); status.textContent = ""; };
    wireFilters();
    const np = document.getElementById("newp");
    if (np) np.onclick = () => { Player.reset(); newPractice(); render(); Player.load().then(() => draw(document.getElementById("roll"), 0)).catch(() => {}); };

    app.querySelectorAll("[data-hint]").forEach(b => (b.onclick = () => {
      const h = nextHint(b.dataset.hint); if (!h) return;
      (S.hints = S.hints || []).push(h); save(); Player.stop(); render();
    }));
    const yr = document.getElementById("year"), yv = document.getElementById("yv");
    let yearTouched = S.year != null;
    if (yr) yr.oninput = () => { yv.textContent = yr.value; yearTouched = true; const d = document.getElementById("ydir"); if (d) d.hidden = true; };

    const form = document.getElementById("guess");
    if (form) {
      const submit = skip => {
        const attempt = S.misses + 1;                      // scoring position: misses so far + 1
        const pg = P.performers.map((_, i) => (skip ? "" : document.getElementById("g-p" + i)?.value || ""));
        const pcg = skip ? "" : document.getElementById("g-piece")?.value || "";
        if (!skip && !pg.some(x => x.trim()) && !pcg.trim() && !(yearTouched && !S.yearAt)) return;
        const rec = { p: [], piece: {}, miss: false };
        let progress = false;
        P.performers.forEach((_, i) => {
          if (S.nameAt[i]) { rec.p.push({ g: "", ok: true }); return; }
          const j = P.performers.findIndex((ans, k) => !S.nameAt[k] && nameMatches(pg[i], ans));
          if (j >= 0) { S.nameAt[j] = attempt; progress = true; }
          rec.p.push({ g: skip ? "(skipped)" : pg[i], ok: j >= 0 });
        });
        if (S.pieceAt) rec.piece = { g: "", ok: true };
        else {
          const gk = CAT.pieceKeyOf[norm(pcg)];
          const ok = !skip && (norm(pcg) === norm(P.piece) || (!!gk && (gk === P.pieceKey || (P.acceptKeys || []).includes(gk))));
          const comp = !ok && !!pcg && composerOf(pcg) === composerOf(P.piece) && !composerRevealed();   // no credit once a hint has given the composer away
          if (ok) { S.pieceAt = attempt; progress = true; }
          if (comp && !S.composerAt) { S.composerAt = attempt; progress = true; }
          rec.piece = { g: skip ? "(skipped)" : pcg, ok, comp };
        }
        if (!S.yearAt && !skip && yearTouched && yr) {
          const yg = +yr.value, ok = yearOff(yg) <= YEAR_TOL;
          S.year = yg;
          if (ok) { S.yearAt = attempt; progress = true; }
          rec.y = { g: yg, ok };
        }
        if (!skip && !progress && !pg.some(x => x.trim()) && !pcg.trim() && !rec.y) return;
        if (!progress) { S.misses++; rec.miss = true; }   // only misses play more
        S.guesses.push(rec);
        if (allSolved() || S.misses >= MAX_MISSES) { S.done = true; recordStats(); }
        save(); Player.stop(); render();
      };
      form.onsubmit = e => { e.preventDefault(); form.querySelectorAll(".suggest").forEach(x => (x.hidden = true)); submit(false); };
      document.getElementById("skip").onclick = () => submit(true);
    }
    const copy = document.getElementById("copy");
    if (copy) copy.onclick = async () => {
      const box = document.querySelector(".share");
      try { await navigator.clipboard.writeText(box.textContent); copy.textContent = "Copied"; }
      catch (e) { const r = document.createRange(); r.selectNodeContents(box); const s = getSelection(); s.removeAllRanges(); s.addRange(r); copy.textContent = "Selected, now copy"; }
    };
    const full = document.getElementById("full");
    if (full) full.onclick = () => { DRAW_LIMIT = 60; window.scrollTo({ top: 0, behavior: "smooth" }); document.getElementById("status").textContent = "PLAYING"; Player.play(60, tick, () => { status.textContent = ""; }); };
  }

  function shareText() {
    const rows = S.guesses.map(g => (g.miss ? "⬛" : "🟩")).join("");
    return `Whose Hands No. ${DAY + 1} · ${total()}/10\n${P.kind === "record" ? "Performers" : "Pianist"} ${allNames() ? "✅" : "❌"}  Piece ${S.pieceAt ? "✅" : S.composerAt ? "🟨" : "❌"}  Year ${S.yearAt ? "✅" : "❌"}\n${rows}${S.hints && S.hints.length ? ` · 💡${S.hints.length}` : ""}\nhttps://whosehands.github.io`;
  }
  function resultHTML() {
    const daily = MODE === "daily";
    const st = store.get(daily ? "wh2-stats" : "wh3-practice-stats", { played: 0, total: 0, best: 0 });
    const yr = P.yearMin === P.yearMax ? P.yearMin : `${P.yearMin}–${P.yearMax}`;
    const fmt = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
    return `<section class="panel result">
      <div class="row"><h2>${allNames() ? (P.kind === "record" ? "You knew them." : "You knew those hands.") : "The answer"}</h2><span class="label">${daily ? "Result" : "Practice result"}</span></div>
      <div class="score">${total()}<small> / 10</small></div>
      <dl class="answer">
        <dt>${P.performers.length > 1 ? "Performers" : esc(roleLabel(0))}</dt><dd><b>${P.performers.map((p, i) => esc(p) + (P.performers.length > 1 ? ` <span class="pts">${esc(roleLabel(i).toLowerCase())}</span>` : "") + (P.performerDates && P.performerDates[p] ? ` <span class="pts">(${esc(P.performerDates[p])})</span>` : "")).join("<br>")}</b>${P.credits ? `<br><span class="pts">${esc(P.credits)}</span>` : ""}</dd>
        <dt>Piece</dt><dd>${esc(P.piece)}${P.movement ? `<br>${P.movement === "selections" ? "Excerpts" : "Part: " + esc(P.movement)}` : ""}${P.arranged ? `<br><span class="pts">${P.kind === "record" ? "Arranged" : "Arranged for piano"}</span>` : ""}${P.rollLabel ? `<br><span class="pts">${P.kind === "record" ? "Record label" : "Roll label"}: ${esc(P.rollLabel)}</span>` : ""}</dd>
        <dt>Clip</dt><dd>Starts ${fmt(Player.start)} into the ${P.kind === "record" ? "record" : "roll"}</dd>
        <dt>Recorded</dt><dd>${esc(String(yr))}${P.yearExact ? "" : " (published; exact date unknown)"}</dd>
        <dt>Your year</dt><dd>${S.year ?? "—"} · ${yearPts()} pt${yearPts() === 1 ? "" : "s"}</dd>
        <dt>Source</dt><dd>${P.kind === "record" ? esc(P.format) : "Piano roll" + (P.rollNumber ? " no. " + esc(P.rollNumber) : "")} · <a href="${esc(P.source)}" target="_blank" rel="noopener">${P.kind === "record" ? "Library of Congress" : "Stanford"} record</a></dd>
      </dl>
      <div class="controls"><button class="btn" id="full">▶ Keep listening (60s)</button>${daily ? "" : `<button class="btn primary" onclick="document.getElementById('newp').click()">Next puzzle</button>`}</div>
      ${daily ? `<div class="share">${esc(shareText())}</div><div class="controls"><button class="btn primary" id="copy">Copy result</button><a class="btn" href="#practice">Practice more</a></div>` : ""}
      <div class="stats"><div><b>${st.played}</b><span>Played</span></div><div><b>${st.played ? (st.total / st.played).toFixed(1) : "–"}</b><span>Avg score</span></div><div><b>${st.best}</b><span>Best</span></div></div>
    </section>`;
  }

  /* ---------- boot ---------- */
  fetch("data/catalog.json").then(r => r.json()).then(cat => {
    CAT = cat;
    BY_ID = Object.fromEntries(cat.recordings.map(r => [r.id, r]));
    DAY = Math.max(0, dayIndex(cat.epoch));
    CAT.allPerformers = [...new Set(cat.recordings.flatMap(r => r.performers))];
    CAT.countBy = {}; cat.recordings.forEach(r => r.performers.forEach(p => (CAT.countBy[p] = (CAT.countBy[p] || 0) + 1)));
    CAT.nameOptions = [...new Set(CAT.allPerformers.concat(DECOYS))].sort((a, b) => surname(a).localeCompare(surname(b)));
    CAT.pieceKeyOf = {};
    (cat.pieceAliases || []).concat(cat.pieceOptions || []).forEach(([n, k]) => { CAT.pieceKeyOf[norm(n)] = k; });
    cat.recordings.forEach(r => { CAT.pieceKeyOf[norm(r.piece)] = r.pieceKey || norm(r.piece); });
    CAT.pieceOptions = [...new Set((cat.pieceOptions || []).map(o => o[0]))].sort();   // the build lists every answer once
    CAT.nameIndex = index(CAT.nameOptions); CAT.pieceIndex = index(CAT.pieceOptions);
    const route = () => (location.hash === "#changelog" ? renderChangelog() : setMode(location.hash === "#practice" ? "practice" : "daily"));
    window.addEventListener("hashchange", route);
    document.addEventListener("visibilitychange", () => { if (document.hidden) { Player.stop(); const st = document.getElementById("status"); if (st) st.textContent = ""; } });
    window.addEventListener("resize", () => { const c = document.getElementById("roll"); if (c) draw(c, 0); });
    route();
  }).catch(e => {
    app.insertAdjacentHTML("beforeend", `<div class="panel"><h2>The recordings didn't load.</h2><p class="how">Check your connection and reload the page.</p></div>`);
    console.error(e);
  });
})();
