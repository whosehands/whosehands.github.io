/* Whose Hands — a daily guessing game for historic recordings.
   Rolls: Stanford University Piano Roll Archive (CC BY-NC-SA 4.0).
   Records: Library of Congress National Jukebox (public domain in the US) and Wikimedia Commons (public domain).
   Piano sound: Salamander Grand Piano V3 by Alexander Holm (CC BY 3.0). MIDI parsing: @tonejs/midi (MIT). MP3 encoding: LAME via lamejs (LGPL). */
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
  // The year is solved only by the exact year. Every year guess earns points by how close it is and how early it came:
  // 2, 1.5 or 1 for the exact year (tries 1-2, 3-4, 5+), half a point less for each year off. The best guess counts.
  const yearPtsAt = a => (a ? (a <= 2 ? 2 : a <= 4 ? 1.5 : 1) : 0);
  const YEAR_TOL = 2;                                   // only for games saved under the old rule
  const yearOff = y => (y < P.yearMin ? P.yearMin - y : y > P.yearMax ? y - P.yearMax : 0);
  const yearGuessPts = (y, a) => Math.max(0, yearPtsAt(a) - 0.5 * yearOff(y));
  const yearPts = () => (S.yearBest !== undefined ? S.yearBest : yearPtsAt(S.yearAt));
  const namesScore = () => S.nameAt.reduce((s, a) => s + namePts(a) / P.performers.length, 0);
  const pieceScore = () => (S.pieceAt ? piecePts(S.pieceAt) : S.setAt ? 2 : S.composerAt ? 1 : 0);   // the right set without the piece: 2
  const total = () => Math.round((namesScore() + pieceScore() + yearPts()) * 10) / 10;
  const allSolved = () => allNames() && !!S.pieceAt && !!S.yearAt;
  const allNames = () => S.nameAt.every(Boolean);

  /* ---------- audio ---------- */
  // Clips are scheduled on the audio clock up front, so they stop on time even when the tab is in the background.
  const Player = {
    forId: null, song: null, notes: null, el: null, start: 0, ctx: null, fx: null, sources: [], samplesLoading: null, loading: null, playing: false, raf: 0,
    reset() { this.stop(); this.forId = null; this.song = null; this.notes = null; this.loading = null; if (this.el) { this.el.src = ""; this.el = null; } this.start = 0; },
    audio() { if (!this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)(); return this.ctx; },
    loadSamples() {                            // the middle velocity layer is enough to start; the others keep loading
      if (!this.samplesLoading) { const ctx = this.audio(); this.samplesLoading = Piano.loadLayer(ctx, 9); this.samplesLoading.then(() => Piano.loadAll(ctx)).catch(() => {}); }
      return this.samplesLoading;
    },
    load() {                                   // prepare the current recording and pick the segment
      if (this.forId === P.id && this.loading) return this.loading;
      this.reset(); this.forId = P.id;
      this.loading = P.kind === "record" ? this.loadRecord() : this.loadRoll();
      return this.loading;
    },
    async loadRoll() {
      const midi = new Midi(await (await fetch(P.midi)).arrayBuffer());
      const song = Piano.prepare(midi);
      song.notes.forEach(n => (n.dur = Math.max(0.05, n.off - n.time)));
      this.song = song; this.notes = song.notes;
      const notes = song.notes;
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
      const resumed = P.kind === "record" ? null : this.audio().resume();   // must begin inside the click
      await this.load();
      this.stop();
      if (P.kind === "record") {
        const a = this.el; a.currentTime = this.start; await a.play();
        this.playing = true;
        const check = () => { if (this.playing && (a.currentTime - this.start >= secs || a.ended)) this.stop(onEnd); };
        a.ontimeupdate = check;                                    // keeps firing in a background tab
        this.poll = setInterval(check, 200);
        const loop = () => { if (!this.playing) return; onTick && onTick(Math.min(a.currentTime - this.start, secs)); this.raf = requestAnimationFrame(loop); };
        return loop();
      }
      await Promise.all([resumed, this.loadSamples()]);
      const ctx = this.ctx, t0 = this.start, at = ctx.currentTime + 0.08;
      this.fx = Piano.chain(ctx, ctx.destination);
      this.sources = Piano.schedule(ctx, this.fx.input, this.song, { from: t0, to: t0 + secs, at, cut: t0 + secs + 0.6 });
      this.playing = true;
      this.poll = setTimeout(() => this.stop(onEnd), (secs + 1.6) * 1000);   // only tidies up: the notes already end on time
      const loop = () => { if (!this.playing) return; onTick && onTick(Math.max(0, Math.min(ctx.currentTime - at, secs))); this.raf = requestAnimationFrame(loop); };
      loop();
    },
    stop(onEnd) {
      clearInterval(this.poll); clearTimeout(this.poll);
      if (this.el) { this.el.pause(); this.el.ontimeupdate = null; }
      if (this.fx) {
        const fx = this.fx, src = this.sources;
        fx.master.gain.setTargetAtTime(0, this.ctx.currentTime, 0.04);
        setTimeout(() => { src.forEach(x => { try { x.stop(); } catch (e) {} }); fx.master.disconnect(); }, 400);
        this.fx = null; this.sources = [];
      }
      cancelAnimationFrame(this.raf);
      const was = this.playing; this.playing = false;
      if (was && onEnd) onEnd();
    }
  };

  const srcName = r => (/wikimedia\.org/.test(r.source || "") ? "Wikimedia Commons" : "Library of Congress");
  /* ---------- downloads ---------- */
  const fileBase = (r = P) => `${r.performers.join(", ")} – ${r.piece.split(" – ").slice(1).join(" – ") || r.piece} (${r.yearMin})`.replace(/[\\/:*?"<>|]+/g, "").slice(0, 150);
  let lameLoading = null;
  const loadLame = () => (lameLoading = lameLoading || new Promise((res, rej) => { const s = document.createElement("script"); s.src = "vendor/lame-1.2.1.min.js"; s.onload = res; s.onerror = rej; document.head.appendChild(s); }));
  async function downloadRoll(rec, fmt, btn) {     // renders the whole roll in the browser, on the game's piano
    const label = btn.textContent; btn.disabled = true;
    try {
      const ctx = Player.audio();
      btn.textContent = "Loading the piano…";
      const songP = fetch(rec.midi).then(r => r.arrayBuffer()).then(b => Piano.prepare(new Midi(b)));
      const [song] = await Promise.all([songP, Piano.loadAll(ctx), fmt === "mp3" ? loadLame() : null]);
      const blob = await (fmt === "wav" ? Piano.renderWav : Piano.renderMp3)(song, p => (btn.textContent = `Rendering ${Math.round(p * 100)}%`));
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = fileBase(rec) + "." + fmt;
      document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 60000);
      btn.textContent = label;
    } catch (e) { console.error(e); btn.textContent = "Couldn't render. Try again"; }
    btn.disabled = false;
  }

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
    return { id, frac, guesses: [], misses: 0, nameAt: BY_ID[id].performers.map(() => 0), pieceAt: 0, setAt: 0, setTried: [], composerAt: 0, year: null, yearAt: 0, yearBest: 0, hints: [], done: false };
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
    if (P.kind !== "record") Player.loadSamples().catch(() => {});
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
  // Quiz-bowl order: each kind starts with specific, little-known facts and gets more obvious.
  // Facts the player already has are skipped (no composer clues once the composer is known).
  const knowsComposer = () => !!(S.composerAt || S.pieceAt || S.setAt || composerRevealed());
  const fillClue = (t, i) => t.replace(/\{Who\}/g, whoOf(i)).replace(/\{Composer\}/g, "The composer").replace(/\{It\}/g, "The work");
  const byLevel = list => list.map((c, n) => [c, n]).sort((a, b) => (a[0].lvl - b[0].lvl) || (a[1] - b[1])).map(x => x[0]);
  function hintLadder(kind, i) {
    const out = [], y = P.yearMin, C = CAT.clues || {};
    if (kind === "who") {
      const name = P.performers[i], who = whoOf(i), d = (P.performerDates || {})[name];
      byLevel((C.people || {})[name] || []).forEach(c => out.push(fillClue(c.t, i)));
      const about = (P.performerAbout || {})[name];
      if (about) out.push(`${who} was ${aAn(about)}`);
      if (born(d)) out.push(`${who} ${lifeText(d)}`);
      const words = name.split(/\s+/).filter(Boolean);
      if (roleOf(i) === "orchestra" || /orchestra|band|quartet|trio|chorus|ensemble|company|choir/i.test(name)) out.push(`The name starts with “${name[0]}”`);
      else out.push(`${who}'s initials are ${words.filter(w => /^\p{Lu}/u.test(w)).map(w => w[0] + ".").join(" ")}`);
    } else if (kind === "what") {
      const comp = !knowsComposer();
      const facts = ((C.works || {})[P.pieceKey] || []).concat(comp ? ((C.composers || {})[P.composer] || []) : []);
      byLevel(facts).forEach(c => out.push(fillClue(c.t, 0)));
      // the kind of music, only where the sound doesn't already tell you (a singer could be in an opera or an art song)
      if (P.kind === "record" && P.genre === "Opera & stage") out.push("It's from an opera or other stage work, not a concert song");
      if (P.kind === "record" && P.genre === "Art songs") out.push("It's a concert song, not from an opera");
      if (P.kind !== "record" && P.genre === "Opera & stage") out.push("It's a piano version of music from an opera or other stage work");
      if (P.kind !== "record" && P.genre === "Orchestral") out.push("It's a piano version of orchestral music");
      if (comp) {
        if (P.composerAbout) out.push(`The composer was ${aAn(P.composerAbout)}`);
        if (born(P.composerDates)) out.push(`The composer ${lifeText(P.composerDates)}`);
        out.push({ text: `Composer: ${P.composer}`, reveals: "composer" });
      }
      const title = P.piece.split(" – ").slice(1).join(" – ") || P.piece, form = title.match(FORMS), key = title.match(/\bin ([A-G](?:[-‐ ]?(?:flat|sharp)|♭|♯)? (?:major|minor))/i);
      if (form && !S.setAt) out.push(`Kind of piece: ${form[1].charAt(0).toUpperCase() + form[1].slice(1).toLowerCase()}`);
      if (key) out.push(`Key: ${key[1].replace("♭", "-flat").replace("♯", "-sharp")}`);
      if (!form && !S.setAt) out.push(`The title starts with “${title.replace(/^[^\p{L}]+/u, "")[0]}”`);
    } else {
      const ev = P.yearMin === P.yearMax && (C.years || {})[y];
      if (ev && ev.length) out.push(`It was recorded the year ${ev[Math.floor(seeded(y + P.id.length) * ev.length)]}`);
      const dec = n => Math.floor(n / 10) * 10, range = `Recorded between ${P.yearMin} and ${P.yearMax}`;
      const cb = born(P.composerDates), cd = died(P.composerDates);
      if (cd && cd < y) out.push(`The composer had died ${y - cd} year${y - cd > 1 ? "s" : ""} before it was recorded`);
      else if (cd === y) out.push("The composer died the year it was recorded");
      else if (cb) out.push(`The composer was alive, about ${y - cb} years old`);
      const pi = P.performers.findIndex(n => born((P.performerDates || {})[n]));
      if (pi >= 0) out.push(`${whoOf(pi)} was about ${y - born(P.performerDates[P.performers[pi]])} years old`);
      out.push(dec(P.yearMin) === dec(P.yearMax) ? `Recorded in the ${dec(y)}s` : range);
      const lo = y - (y % 5);
      if (P.yearMax <= lo + 4) out.push(`Recorded between ${lo} and ${lo + 4}`);
      else if (dec(P.yearMin) === dec(P.yearMax)) out.push(range);
    }
    return out.map(h => (typeof h === "string" ? { text: h } : h));
  }
  function takenHints() {                  // the hints opened so far, in order (each one stores its own text)
    return (S.hints || []).filter(h => h.t).map(h => ({ text: h.t, reveals: h.reveals, kind: HINT_KINDS.find(x => x[0] === h.k)[1] }));
  }
  const composerRevealed = () => (S.hints || []).some(h => h.reveals === "composer");
  function nextHint(kind) {                // the next clue of this kind, or null if there's nothing left to give
    const i = kind === "who" ? S.nameAt.findIndex(a => !a) : 0;
    if (kind === "who" ? i < 0 : kind === "what" ? S.pieceAt : S.yearAt) return null;
    const given = new Set((S.hints || []).map(h => h.t));
    const c = hintLadder(kind, i).find(h => !given.has(h.text));
    return c ? { k: kind, i, t: c.text, reveals: c.reveals } : null;
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

  function tabsHTML(on) {
    const t = [["daily", "#", "Daily"], ["practice", "#practice", "Practice"], ["score", "#score", "Score"], ["library", "#library", "Library"]];
    return `<nav class="tabs" aria-label="Mode">${t.map(([k, h, l]) => `<a href="${h}" class="${on === k ? "on" : ""}" ${on === k ? 'aria-current="page"' : ""}>${l}</a>`).join("")}</nav>`;
  }

  /* ---------- Guess the Score: a few bars of sheet music; name the piece ---------- */
  const SC = { data: null, vrv: null, tk: null, item: null, st: null, systems: [], midi: null, timemap: null, song: null, practice: false };
  const SC_MAX = 6;
  const scPts = a => (a ? [0, 5, 4, 3, 2, 1, 1, 1][a] : 0);
  const scTotal = () => (SC.st.pieceAt ? scPts(SC.st.pieceAt) : SC.st.setAt ? 2 : SC.st.composerAt ? 1 : 0);
  const scKey = () => (SC.practice ? "wh4-score-practice" : "wh4-score-day-" + DAY);
  async function scLoad() {
    if (!SC.data) {
      SC.data = await (await fetch("data/scores.json")).json();
      const names = [...new Set(SC.data.pieces.filter(p => !p.set).map(p => p.piece).concat(Object.values(SC.data.sets).map(x => x.name)))].sort();
      SC.keyOf = {}; SC.data.pieces.forEach(p => { SC.keyOf[norm(p.piece)] = p.answerKey; });
      Object.entries(SC.data.sets).forEach(([k, x]) => { SC.keyOf[norm(x.name)] = "set:" + k; });
      SC.index = index(names);
      // keyboard music most days, a song or a string quartet now and then, so the many songs don't crowd out everything else
      const grp = p => (/song/i.test(p.genre || "") ? "song" : /quartet|trio|violin|cello/i.test(p.genre || "") ? "chamber" : "keys");
      const pools = { keys: [], song: [], chamber: [] };
      SC.data.pieces.forEach((p, i) => pools[grp(p)].push([seeded(i * 7 + 3), i]));
      Object.values(pools).forEach(l => l.sort((a, b) => a[0] - b[0]));
      const pattern = ["keys", "keys", "song", "keys", "chamber", "keys", "song"], pos = { keys: 0, song: 0, chamber: 0 }, order = [];
      for (let n = 0; order.length < SC.data.pieces.length && n < SC.data.pieces.length * 3; n++) {
        const g = pattern[n % pattern.length], l = pools[g];
        if (l.length) order.push(l[pos[g]++ % l.length][1]);
      }
      SC.order = order; SC.pools = pools;
    }
    if (!SC.vrv) {
      SC.vrv = (async () => {
        const [{ default: createModule }, { VerovioToolkit }] = await Promise.all([import("./vendor/verovio-6.4.1-hum.mjs"), import("./vendor/verovio-6.4.1.mjs")]);
        const tk = new VerovioToolkit(await createModule());
        return tk;
      })();
    }
    SC.tk = await SC.vrv;
  }
  function scFresh(i, frac) { return { i, pid: SC.data.pieces[i].id, frac, guesses: [], misses: 0, pieceAt: 0, setAt: 0, setTried: [], composerAt: 0, done: false }; }
  function scPick(practice) {
    SC.practice = practice;
    let st = store.get(scKey(), null);
    const byId = st && st.pid ? SC.data.pieces.findIndex(p => p.id === st.pid) : -1;   // a saved game keeps its piece even if the list changes
    if (byId >= 0) st.i = byId;
    if (!practice) { const want = SC.order[DAY % SC.order.length]; if (!st || byId < 0) st = scFresh(want, seeded(DAY * 31 + 5)); }
    else if (!st || byId < 0) {
      const g = ["keys", "keys", "keys", "song", "chamber"][Math.floor(Math.random() * 5)], l = SC.pools[g].length ? SC.pools[g] : SC.pools.keys;
      st = scFresh(l[Math.floor(Math.random() * l.length)][1], Math.random());
    }
    SC.st = st; SC.item = SC.data.pieces[st.i];
  }
  // Long scores (a whole string quartet) are slow to lay out, so only a 40-bar window is engraved, plus the opening when a clue calls for it.
  const SC_WINDOW = 40;
  function scSystemsOf(tk, box, list) {
    for (let p = 1; p <= tk.getPageCount(); p++) {
      const holder = document.createElement("div"); holder.className = "sc-page"; holder.innerHTML = tk.renderToSVG(p); box.appendChild(holder);
      const root = holder.querySelector("svg"), r0 = root.getBoundingClientRect();
      holder.querySelectorAll("g.system").forEach((g, k) => {
        // measure by the bars themselves: a system's own box can include stray layout far below the music
        const rs = [...g.querySelectorAll("g.measure > g.staff")].map(m => m.getBoundingClientRect()).filter(r => r.width && r.height);
        if (!rs.length) return;
        const L = Math.min(...rs.map(r => r.left)), T = Math.min(...rs.map(r => r.top)), R = Math.max(...rs.map(r => r.right)), B = Math.max(...rs.map(r => r.bottom));
        const gl = g.getBoundingClientRect().left;
        list.push({ pageEl: root, k, box: [Math.min(L, gl) - r0.left - 6, T - r0.top - 34, R - Math.min(L, gl) + 12, B - T + 64] });   // room for tempo marks above and dynamics below
      });
    }
    return list;
  }
  async function scRenderPiece() {
    const tk = SC.tk, box = document.getElementById("sc-work"), it = SC.item;
    const file = it.file || "scores/" + it.id + ".krn", res = await fetch(file);
    const data = file.endsWith(".mxl") ? await res.arrayBuffer() : await res.text();
    const w = Math.max(320, Math.min(760, app.clientWidth || 560));
    tk.setOptions({ pageWidth: w < 500 ? 1500 : 1800, pageHeight: 60000, adjustPageHeight: true, breaks: "auto", header: "none", footer: "none", scale: 33,
      pageMarginTop: 20, pageMarginBottom: 20, pageMarginLeft: 20, pageMarginRight: 20, spacingSystem: 10, systemMaxPerPage: 30 });
    if (typeof data === "string") tk.loadData(data); else tk.loadZipDataBuffer(data);
    const M = it.measures || 0;
    SC.windowed = M > SC_WINDOW + 16;
    box.innerHTML = "";
    SC.opening = null;
    if (SC.windowed) {
      const s0 = 1 + Math.floor(SC.st.frac * (M - SC_WINDOW));
      SC.winStart = s0;
      tk.select({ measureRange: `${s0}-${s0 + SC_WINDOW - 1}` }); tk.redoLayout();
    }
    SC.systems = scSystemsOf(tk, box, []);
    if (SC.windowed && SC.winStart > 1) {
      tk.select({ measureRange: "1-6" }); tk.redoLayout();
      SC.opening = scSystemsOf(tk, box, [])[0] || null;
    }
  }
  function scShown() {                       // which systems are visible: the chosen one, then one more after, before, after ...
    const n = SC.systems.length, st = SC.st;
    const start = Math.min(n - 1, Math.max(n > 2 ? 1 : 0, Math.floor((SC.windowed ? 0.35 : st.frac) * n)));
    const extra = SC.whole ? n : Math.min(st.misses, 3);
    let a = start, b = start;
    for (let i = 0; i < extra; i++) { if (i % 2 === 0 && b < n - 1) b++; else if (a > 0) a--; else if (b < n - 1) b++; }
    const list = []; for (let i = a; i <= b; i++) list.push(SC.systems[i]);
    const opening = SC.windowed ? SC.opening : a > 0 ? SC.systems[0] : null;
    if (scClues().some(c => c.startsWith("The opening")) && opening && !SC.whole) list.unshift(opening);   // the opening, as a clue
    return SC.whole ? list.slice(0, 60) : list;
  }
  function scSystemSVG(sys) {
    const page = sys.pageEl.cloneNode(true);
    const inner = page.querySelector("svg.definition-scale");     // keep the page's own size, or the whole page shrinks into the crop
    if (inner) { inner.setAttribute("width", parseFloat(page.getAttribute("width"))); inner.setAttribute("height", parseFloat(page.getAttribute("height"))); }
    page.querySelectorAll("g.system").forEach((g, k) => { if (k !== sys.k) g.remove(); });
    const [x, y, w, h] = sys.box;
    page.setAttribute("viewBox", `${x} ${y} ${w} ${h}`); page.setAttribute("width", "100%"); page.removeAttribute("height");
    page.setAttribute("preserveAspectRatio", "xMinYMin meet"); page.style.aspectRatio = `${w} / ${h}`;
    return page;
  }
  function scClues() {                       // music facts only, from less to more obvious; nothing the score already shows
    const it = SC.item, c = [];
    if (it.words) c.push(`Words by ${it.words}`);
    if (it.year) c.push(`Written in ${it.year}`);
    if (it.language) c.push(`Sung in ${it.language}`);
    if (it.key) c.push(`Key: ${it.key}`);
    const cc = (CAT.clues || {}).composers || {}, full = Object.keys(cc).filter(n => n.split(" ").pop() === it.composer.split(" ").pop() && (it.composer.includes(" ") ? n === it.composer || n.endsWith(it.composer.split(" ").pop()) : true));
    if (full.length === 1) { const f = (cc[full[0]] || []).find(x => x.lvl <= 2); if (f) c.push(f.t.replace(/\{Composer\}/g, "The composer")); }
    if (it.genre && !/song|quartet/i.test(it.genre)) c.push(`Kind of piece: ${it.genre}${it.movement ? ` (${it.movement.replace(/:.*/, "").toLowerCase()})` : ""}`);
    c.push(`Composer: ${it.composer}`);
    c.push("The opening bars are now shown at the top");
    const num = it.piece.match(/(Op\. ?\d+[^,]*|K\. [\w. ]+|Hob\. [\w:]+|BWV \d+|D\. ?\d+|S\.\s?\d+)$/);
    if (num) c.push(`Catalogue number: ${num[1]}`);
    else c.push(`The title starts with “${((it.piece.split(" – ")[1] || "").replace(/^[^\p{L}]+/u, ""))[0]}”`);
    return c.slice(0, Math.min(SC.st.misses, 6));
  }
  const scComposerShown = () => scClues().some(c => c.startsWith("Composer:"));
  function scSave() { store.set(scKey(), SC.st); }
  async function renderScore(practice) {
    Player.stop(); MODE = "score";
    app.innerHTML = `<header><h1>Whose <em>Hands</em></h1><span class="meta">${practice ? "Score practice" : `Score No. ${DAY + 1}`}</span></header>
      ${tabsHTML("score")}
      <p class="how">Name the piece from a few bars of its score. Each miss shows more of the score and a clue. No sound: just the notes.</p>
      <section class="panel"><p class="how" id="sc-loading">Loading the score engine (about 4 MB, once)…</p></section><div id="sc-work" class="sc-work" aria-hidden="true"></div>
      <footer><span>${practice ? "Practice scores are random." : "A new score every day at midnight."} Scores: Chopin's first editions encoded by the Fryderyk Chopin Institute (CC BY 4.0); Mozart and Haydn sonatas by Craig Stuart Sapp (CC BY-NC-SA 4.0); the Distant Listening Corpus of the Digital and Cognitive Musicology Lab, EPFL (CC BY-NC-SA 4.0); OpenScore Lieder and String Quartets (CC0). Engraved with Verovio (LGPL).</span>
      <span><a href="#changelog">What's new</a></span></footer>`;
    try { await scLoad(); } catch (e) { console.error(e); document.getElementById("sc-loading").textContent = "The score engine didn't load. Reload the page to try again."; return; }
    if (MODE !== "score") return;
    scPick(practice); SC.whole = false;
    await scRenderPiece();
    scDraw();
  }
  function scDraw() {
    const st = SC.st, it = SC.item, set = it.set && SC.data.sets[it.set];
    const shown = scShown();
    const fieldHTML = st.setAt && !st.pieceAt && set
      ? `<div class="field part"><div class="row"><span class="label">Piece</span><span class="chip part">Set ✓ · now pick the piece</span></div>
          <input type="text" value="${esc(set.name)}" disabled><label class="label" for="sc-member">Which one?</label>
          <select id="sc-member"><option value="">Choose a piece from the set…</option>${set.members.map(([n, k]) => `<option value="${esc(k)}" ${st.setTried.includes(k) ? "disabled" : ""}>${st.setTried.includes(k) ? "✕ " : ""}${esc(n.split(" – ")[1])}</option>`).join("")}</select></div>`
      : `<div class="field"><div class="row"><label class="label" for="sc-guess">Piece</label><span class="pts">up to 5 pts${scComposerShown() || st.composerAt ? "" : " · right composer 1"}</span></div>
          <input type="text" id="sc-guess" placeholder="Start typing a title, set or composer"></div>`;
    const panel = document.querySelector("#app .panel");
    panel.innerHTML = `
      <div class="row"><h2>What piece is this?</h2><span class="pts">${st.misses}/${SC_MAX} misses</span></div>
      <div class="sc-systems" id="sc-systems"></div>
      ${st.done && !SC.whole ? `<div class="controls"><button class="btn" id="sc-whole">${SC.windowed ? "Show more of the score" : "Show the whole score"}</button></div>` : ""}
      ${st.done ? "" : `<form id="sc-form" autocomplete="off">${fieldHTML}
        <div class="controls"><button class="btn primary" type="submit">Guess</button><button class="btn" type="button" id="sc-skip">Skip, show more</button></div></form>`}
      ${scClues().length ? `<div><div class="label">Clues</div><ul class="hints">${scClues().map(c => `<li>${esc(c)}</li>`).join("")}</ul></div>` : ""}
      ${st.guesses.length ? `<ul class="tries">${st.guesses.map(g => `<li><span class="n">${g.ok ? "✓" : "✕"}</span><span class="g ${g.ok ? "ok" : g.part ? "part" : "no"}">${esc(g.g || "—")}</span></li>`).join("")}</ul>` : ""}
      ${st.done ? `<div class="result-inline"><div class="score">${scTotal()}<small> / 5</small></div>
        <dl class="answer"><dt>Piece</dt><dd><b>${esc(it.piece)}</b>${it.movement ? `<br>${esc(it.movement)}` : ""}</dd>
        <dt>Edition</dt><dd>${esc(it.by)} · ${esc(it.license)}</dd></dl>
        <div class="controls">${SC.practice ? "" : `<button class="btn primary" id="sc-copy">Copy result</button>`}<button class="btn ${SC.practice ? "primary" : ""}" id="sc-next">${SC.practice ? "Next score" : "Practice another score"}</button></div></div>` : ""}`;
    const holder = document.getElementById("sc-systems");
    shown.forEach(sys => holder.appendChild(scSystemSVG(sys)));
    const form = document.getElementById("sc-form");
    if (form) {
      const g = document.getElementById("sc-guess"); if (g) suggest(g, SC.index);
      const submit = skip => {
        const attempt = st.misses + 1, rec = { g: "", ok: false, part: false };
        const mem = document.getElementById("sc-member");
        if (mem) {
          const k = skip ? "" : mem.value; if (!skip && !k) return;
          rec.g = skip ? "(skipped)" : mem.options[mem.selectedIndex].text;
          if (k === it.answerKey) { st.pieceAt = attempt; rec.ok = true; } else if (k) st.setTried.push(k);
        } else {
          const txt = skip ? "" : g.value.trim(); if (!skip && !txt) return;
          const k = SC.keyOf[norm(txt)] || "";
          rec.g = skip ? "(skipped)" : txt;
          if (k === it.answerKey) { st.pieceAt = attempt; rec.ok = true; }
          else if (it.set && k === "set:" + it.set) { st.setAt = attempt; rec.part = true; }
          else if (!scComposerShown() && !st.composerAt && txt && norm(txt.split(" – ")[0]) === norm(it.composer)) { st.composerAt = attempt; rec.part = true; }
        }
        if (!rec.ok && !rec.part) st.misses++;
        st.guesses.push(rec);
        if (st.pieceAt || st.misses >= SC_MAX) st.done = true;
        if (st.done && !SC.practice) { const s2 = store.get("wh4-score-stats", { played: 0, total: 0, days: {} }); if (s2.days[DAY] === undefined) { s2.days[DAY] = scTotal(); s2.played++; s2.total += scTotal(); store.set("wh4-score-stats", s2); } }
        scSave(); Player.stop(); scDraw();
      };
      form.onsubmit = e => { e.preventDefault(); form.querySelectorAll(".suggest").forEach(x => (x.hidden = true)); submit(false); };
      document.getElementById("sc-skip").onclick = () => submit(true);
    }
    const whole = document.getElementById("sc-whole");
    if (whole) whole.onclick = () => { SC.whole = true; scDraw(); };
    const next = document.getElementById("sc-next");
    if (next) next.onclick = () => { store.set("wh4-score-practice", null); location.hash === "#score-practice" ? renderScore(true) : (location.hash = "#score-practice"); };
    const copy = document.getElementById("sc-copy");
    if (copy) copy.onclick = async () => {
      const txt = `Whose Hands · Score No. ${DAY + 1} · ${scTotal()}/5\n${st.guesses.map(x => (x.ok ? "🟩" : x.part ? "🟨" : "⬛")).join("")}\nhttps://whosehands.github.io/#score`;
      try { await navigator.clipboard.writeText(txt); copy.textContent = "Copied"; } catch (e) { copy.textContent = "Couldn't copy"; }
    };
  }

  /* ---------- library: every recording, searchable, with downloads ---------- */
  const LIB = { q: "", format: "", genre: "", from: YEAR_MIN, to: YEAR_MAX, sort: "year", shown: 50 };
  function libRows() {
    const words = norm(LIB.q).split(" ").filter(Boolean);
    const rows = CAT.recordings.filter(r => {
      if (LIB.format && (LIB.format === "record") !== (r.kind === "record")) return false;
      if (LIB.genre && r.genre !== LIB.genre) return false;
      if (r.yearMax < LIB.from || r.yearMin > LIB.to) return false;
      if (!words.length) return true;
      const hay = norm([r.piece, r.composer, r.performers.join(" "), r.yearMin, r.yearMax, r.label || "", r.genre || "", r.title || ""].join(" "));
      return words.every(w => hay.includes(w));
    });
    const by = { year: r => r.yearMin * 1e4, composer: r => r.composer, performer: r => r.performers[0], piece: r => r.piece.split(" – ").slice(1).join(" – ") };
    const f = by[LIB.sort];
    rows.sort((a, b) => { const x = f(a), y = f(b); return x < y ? -1 : x > y ? 1 : a.yearMin - b.yearMin; });
    return { rows };
  }
  function libItem(r) {
    const roles = r.performers.map((n, i) => { const role = r.roles && r.roles[i]; return esc(n) + (role && role !== "piano" ? ` <span class="pts">${esc(ROLE_NAMES[role] || role)}</span>` : ""); }).join(", ");
    const yr = r.yearMin === r.yearMax ? r.yearMin : `${r.yearMin}–${r.yearMax}`;
    const dl = r.kind === "record"
      ? `<a class="btn small" href="${esc(r.audio)}" target="_blank" rel="noopener" download>MP3</a><a class="btn small" href="${esc(r.source)}" target="_blank" rel="noopener">${srcName(r)}</a>`
      : `<button class="btn small" data-ldl="mp3" data-id="${esc(r.id)}">MP3</button><button class="btn small" data-ldl="wav" data-id="${esc(r.id)}">WAV</button><a class="btn small" href="${esc(r.midi)}" download="${esc(fileBase(r))}.mid">MIDI</a>${r.source ? `<a class="btn small" href="${esc(r.source)}" target="_blank" rel="noopener">Stanford</a>` : ""}`;
    return `<li class="lib-item"><div class="lib-head"><b>${esc(r.piece)}</b><span class="pts">${yr}</span></div>
      <div class="lib-meta">${roles} · ${r.kind === "record" ? "78 record" : "piano roll"}${r.label ? " · " + esc(r.label) : ""} · ${esc(r.genre || "")}</div>
      <div class="controls">${dl}</div></li>`;
  }
  function libList() {
    const { rows } = libRows(), box = document.getElementById("lib-list");
    document.getElementById("lib-count").textContent = `${rows.length} recording${rows.length === 1 ? "" : "s"}`;
    box.innerHTML = rows.slice(0, LIB.shown).map(libItem).join("") || `<li class="how">Nothing matches.</li>`;
    const more = document.getElementById("lib-more");
    more.hidden = rows.length <= LIB.shown;
    box.querySelectorAll("[data-ldl]").forEach(b => (b.onclick = () => downloadRoll(BY_ID[b.dataset.id], b.dataset.ldl, b)));
  }
  function renderLibrary() {
    Player.stop(); MODE = "library";
    const genres = [...new Set(CAT.recordings.map(r => r.genre).filter(Boolean))].sort();
    const years = []; for (let y = YEAR_MIN; y <= YEAR_MAX; y++) years.push(y);
    const opt = (v, l, sel) => `<option value="${esc(v)}" ${sel ? "selected" : ""}>${esc(l)}</option>`;
    app.innerHTML = `<header><h1>Whose <em>Hands</em></h1><span class="meta">Library</span></header>
    ${tabsHTML("library")}
    <p class="how">Every recording in the game. Search by composer, performer, piece or year, and download any of them. Rolls are made into audio in your browser on the game's piano; records come from the Library of Congress and Wikimedia Commons.</p>
    <section class="panel lib">
      <input type="search" id="lib-q" placeholder="Search: Chopin, Caruso, Op. 28, 1912…" value="${esc(LIB.q)}" aria-label="Search recordings">
      <div class="lib-filters">
        <select id="lib-format" aria-label="Format">${opt("", "Rolls and records", !LIB.format)}${opt("roll", "Piano rolls", LIB.format === "roll")}${opt("record", "78 records", LIB.format === "record")}</select>
        <select id="lib-genre" aria-label="Kind of music">${opt("", "All kinds", !LIB.genre)}${genres.map(g => opt(g, g, LIB.genre === g)).join("")}</select>
        <span class="lib-years"><select id="lib-from" aria-label="From year">${years.map(y => opt(y, y, y === LIB.from)).join("")}</select>–<select id="lib-to" aria-label="To year">${years.map(y => opt(y, y, y === LIB.to)).join("")}</select></span>
        <select id="lib-sort" aria-label="Sort by">${[["year", "Sort by year"], ["composer", "Sort by composer"], ["performer", "Sort by performer"], ["piece", "Sort by piece"]].map(([v, l]) => opt(v, l, LIB.sort === v)).join("")}</select>
      </div>
      <div class="pts" id="lib-count"></div>
      <ul class="lib-list" id="lib-list"></ul>
      <button class="btn" id="lib-more">Show more</button>
    </section>
    <footer><span>Rolls: Stanford University Piano Roll Archive (CC BY-NC-SA 4.0). Records: Library of Congress National Jukebox and Wikimedia Commons (public domain). Piano: Salamander Grand Piano V3 by Alexander Holm (CC BY 3.0).</span><span><a href="#changelog">What's new</a></span></footer>`;
    const q = document.getElementById("lib-q");
    let t = 0;
    q.oninput = () => { clearTimeout(t); t = setTimeout(() => { LIB.q = q.value; LIB.shown = 50; libList(); }, 150); };
    [["lib-format", "format"], ["lib-genre", "genre"], ["lib-sort", "sort"]].forEach(([id, k]) => (document.getElementById(id).onchange = e => { LIB[k] = e.target.value; LIB.shown = 50; libList(); }));
    document.getElementById("lib-from").onchange = e => { LIB.from = +e.target.value; libList(); };
    document.getElementById("lib-to").onchange = e => { LIB.to = +e.target.value; libList(); };
    document.getElementById("lib-more").onclick = () => { LIB.shown += 100; libList(); };
    libList();
  }

  /* ---------- changelog ---------- */
  function renderChangelog() {
    Player.stop();
    app.innerHTML = `<header><h1>Whose <em>Hands</em></h1><span class="meta">What's new</span></header>
    ${tabsHTML("")}
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
    const hs = takenHints(), toOpen = S.done ? 0 : S.misses - hs.length;
    const dateStr = new Date().toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
    const tag = daily ? "NO. " + (DAY + 1) : "PRACTICE";
    const fresh = !S.guesses.length && !S.done;

    app.innerHTML = `
    <header><h1>Whose <em>Hands</em></h1><span class="meta">${daily ? `No. ${DAY + 1} · ${esc(dateStr)}` : "Practice"}</span></header>
    ${tabsHTML(daily ? "daily" : "practice")}
    ${fresh ? `<p class="how">${P.kind === "record"
      ? "This is a 78 record. Guess everyone featured on it, the piece, and the year it was recorded."
      : "A pianist recorded this on a piano roll. You hear their exact notes, pedaling and timing on a modern piano. Guess who, what, and the year it was recorded."}
      You hear a random part of the piece. Guess all three together: the sooner you get each one, the more it's worth. The year counts as solved only when it's exact, but a close year still earns points. Right answers keep the clip as it is; each miss plays more and earns a hint, and you choose what it's about.</p>` : ""}
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
        ${pieceFieldHTML()}
        <div class="field year ${S.yearAt ? "solved" : ""}"><div class="row"><label class="label" for="year">Year recorded</label>${S.yearAt ? `<span class="chip">✓</span>` : `<span class="pts">up to 2 pts · closer is worth more</span>`}</div>
          <div class="row"><span class="val" id="yv">${S.year ?? "—"}</span>${!S.yearAt && S.year != null ? `<span class="pts">best so far: ${yearPts()} pt${yearPts() === 1 ? "" : "s"}</span>` : ""}</div>
          <input type="range" id="year" min="${YEAR_MIN}" max="${YEAR_MAX}" step="1" value="${S.year ?? Math.round((YEAR_MIN + YEAR_MAX) / 2)}" ${S.yearAt ? "disabled" : ""} aria-label="Year recorded"></div>
        <div class="controls"><button class="btn primary" type="submit">Guess</button><button class="btn" type="button" id="skip">Skip, play more</button></div>
      </form>`}
      ${hs.length || toOpen > 0 ? `<div class="hintbox"><div class="label">Hints</div>
        ${hs.length ? `<ul class="hints">${hs.map(h => `<li><span class="kind">${h.kind}</span> ${esc(h.text)}</li>`).join("")}</ul>` : ""}
        ${toOpen > 0 ? `<div class="hintpick"><span class="pts">${toOpen === 1 ? "You have a hint. What should it be about?" : `You have ${toOpen} hints. What should the next one be about?`}</span>
          <div class="controls">${HINT_KINDS.map(([k, label]) => `<button class="btn small" type="button" data-hint="${k}" ${nextHint(k) ? "" : "disabled"}>${label}</button>`).join("")}</div></div>` : ""}</div>` : ""}
      ${S.guesses.length ? `<ul class="tries">${S.guesses.map((t, i) => `<li><span class="n">${t.miss ? "✕" : "✓"}</span><span class="g">${t.p.map(x => `<span class="${x.ok ? "ok" : "no"}">${esc(x.g || "—")}</span>`).join(" · ")}<br><span class="${t.piece.ok ? "ok" : t.piece.comp ? "part" : "no"}">${esc(t.piece.g || "—")}</span>${t.y ? ` · <span class="${t.y.ok ? "ok" : t.y.pts ? "part" : "no"}">${t.y.g}</span>${t.y.ok || t.y.pts === undefined ? "" : ` <span class="pts">${t.y.pts} pt${t.y.pts === 1 ? "" : "s"}</span>`}` : ""}</span></li>`).join("")}</ul>` : ""}
    </section>

    ${S.done ? resultHTML() : ""}

    <footer>
      <span>${daily ? "A new recording every day at midnight." : "Practice puzzles are random and don't count toward your daily stats."} Rolls from the <a href="https://supra.stanford.edu" target="_blank" rel="noopener">Stanford University Piano Roll Archive</a> (CC BY-NC-SA 4.0). Records from the <a href="https://www.loc.gov/collections/national-jukebox/" target="_blank" rel="noopener">Library of Congress National Jukebox</a> and <a href="https://commons.wikimedia.org" target="_blank" rel="noopener">Wikimedia Commons</a> (public domain). Piano sound: Salamander Grand Piano V3 by Alexander Holm (CC BY 3.0).</span>
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
      status.textContent = Player.forId === P.id && (Player.notes || Player.el) && (P.kind === "record" || Piano.layerReady(9)) ? "PLAYING" : "LOADING…";
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
    if (yr) yr.oninput = () => { yv.textContent = yr.value; yearTouched = true; };

    const form = document.getElementById("guess");
    if (form) {
      const submit = skip => {
        const attempt = S.misses + 1;                      // scoring position: misses so far + 1
        const pg = P.performers.map((_, i) => (skip ? "" : document.getElementById("g-p" + i)?.value || ""));
        const pcg = skip ? "" : document.getElementById("g-piece")?.value || document.getElementById("g-member")?.value || "";
        if (!skip && !pg.some(x => x.trim()) && !pcg.trim() && !(yearTouched && !S.yearAt)) return;
        const rec = { p: [], piece: {}, miss: false };
        let progress = false;
        P.performers.forEach((_, i) => {
          if (S.nameAt[i]) { rec.p.push({ g: "", ok: true }); return; }
          const j = P.performers.findIndex((ans, k) => !S.nameAt[k] && nameMatches(pg[i], ans));
          if (j >= 0) { S.nameAt[j] = attempt; progress = true; }
          rec.p.push({ g: skip ? "(skipped)" : pg[i], ok: j >= 0 });
        });
        const mem = document.getElementById("g-member");
        if (S.pieceAt) rec.piece = { g: "", ok: true };
        else if (mem) {                                       // the set is known: which piece of it?
          const mk = skip ? "" : mem.value, ok = !!mk && (mk === P.pieceKey || (P.acceptKeys || []).includes(mk));
          if (ok) { S.pieceAt = attempt; progress = true; }
          else if (mk) (S.setTried = S.setTried || []).push(mk);
          rec.piece = { g: skip ? "(skipped)" : mk ? mem.options[mem.selectedIndex].text : "", ok };
        } else {
          const gk = CAT.pieceKeyOf[norm(pcg)];
          const ok = !skip && (norm(pcg) === norm(P.piece) || (!!gk && (gk === P.pieceKey || (P.acceptKeys || []).includes(gk))));
          const comp = !ok && !!pcg && composerOf(pcg) === composerOf(P.piece) && !composerRevealed();   // no credit once a hint has given the composer away
          const isSet = !ok && !!gk && !!P.set && gk === P.set;   // right set: next, pick which piece
          if (ok) { S.pieceAt = attempt; progress = true; }
          if (isSet) { S.setAt = attempt; progress = true; }
          if (comp && !S.composerAt) { S.composerAt = attempt; progress = true; }
          rec.piece = { g: skip ? "(skipped)" : pcg, ok, comp: comp || isSet };
        }
        const lastYear = [...S.guesses].reverse().find(t => t.y);
        if (!S.yearAt && !skip && yearTouched && yr && !(lastYear && lastYear.y.g === +yr.value)) {   // the same year again isn't a new guess
          const yg = +yr.value, ok = yearOff(yg) === 0, pts = yearGuessPts(yg, attempt);
          S.year = yg;
          S.yearBest = Math.max(S.yearBest || 0, pts);
          if (ok) { S.yearAt = attempt; progress = true; }
          rec.y = { g: yg, ok, pts };
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
    app.querySelectorAll("[data-dl]").forEach(b => (b.onclick = () => downloadRoll(P, b.dataset.dl, b)));
    const full = document.getElementById("full");
    if (full) full.onclick = () => { DRAW_LIMIT = 60; window.scrollTo({ top: 0, behavior: "smooth" }); document.getElementById("status").textContent = "PLAYING"; Player.play(60, tick, () => { status.textContent = ""; }); };
  }

  function pieceFieldHTML() {
    const setInfo = P.set && CAT.sets && CAT.sets[P.set];
    if (S.setAt && !S.pieceAt && setInfo) {
      const tried = S.setTried || [];
      return `<div class="field part"><div class="row"><span class="label">Piece</span><span class="chip part">Set ✓ · now pick the piece</span></div>
          <input type="text" value="${esc(setInfo.name)}" disabled aria-label="Set">
          <label class="label" for="g-member">Which one?</label>
          <select id="g-member"><option value="">Choose a piece from the set…</option>${setInfo.members.map(([n, k]) => `<option value="${esc(k)}" ${tried.includes(k) ? "disabled" : ""}>${tried.includes(k) ? "✕ " : ""}${esc(n.split(" – ").slice(1).join(" – ") || n)}</option>`).join("")}</select></div>`;
    }
    return `<div class="field ${S.pieceAt ? "solved" : ""}"><div class="row"><label class="label" for="g-piece">Piece</label>${S.pieceAt ? `<span class="chip">✓</span>` : S.composerAt ? `<span class="chip part">Composer ✓</span>` : `<span class="pts">up to 3 pts${composerRevealed() ? "" : " · right composer 1"}</span>`}</div>
          <input type="text" id="g-piece" placeholder="Start typing a composer, title or set" ${S.pieceAt ? `value="${esc(P.piece)}" disabled` : ""}></div>`;
  }
  function shareText() {
    const rows = S.guesses.map(g => (g.miss ? "⬛" : "🟩")).join("");
    return `Whose Hands No. ${DAY + 1} · ${total()}/10\n${P.kind === "record" ? "Performers" : "Pianist"} ${allNames() ? "✅" : "❌"}  Piece ${S.pieceAt ? "✅" : S.setAt || S.composerAt ? "🟨" : "❌"}  Year ${S.yearAt ? "✅" : yearPts() ? "🟨" : "❌"}\n${rows}${S.hints && S.hints.length ? ` · 💡${S.hints.length}` : ""}\nhttps://whosehands.github.io`;
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
        <dt>Piece</dt><dd>${esc(P.piece)}${P.set && CAT.sets && CAT.sets[P.set] ? `<br><span class="pts">From the set: ${esc(CAT.sets[P.set].name.split(" – ").slice(1).join(" – "))}</span>` : ""}${P.movement ? `<br>${P.movement === "selections" ? "Excerpts" : "Part: " + esc(P.movement)}` : ""}${P.arranged ? `<br><span class="pts">${P.kind === "record" ? "Arranged" : "Arranged for piano"}</span>` : ""}${P.rollLabel ? `<br><span class="pts">${P.kind === "record" ? "Record label" : "Roll label"}: ${esc(P.rollLabel)}</span>` : ""}</dd>
        <dt>Clip</dt><dd>Starts ${fmt(Player.start)} into the ${P.kind === "record" ? "record" : "roll"}</dd>
        <dt>Recorded</dt><dd>${esc(String(yr))}${P.yearExact ? "" : " (published; exact date unknown)"}</dd>
        <dt>Your year</dt><dd>${S.year ?? "—"} · ${yearPts()} pt${yearPts() === 1 ? "" : "s"}</dd>
        <dt>Source</dt><dd>${P.kind === "record" ? esc(P.format) : "Piano roll" + (P.rollNumber ? " no. " + esc(P.rollNumber) : "")} · <a href="${esc(P.source)}" target="_blank" rel="noopener">${P.kind === "record" ? "Library of Congress" : "Stanford"} record</a></dd>
      </dl>
      <div class="dl"><span class="label">Download the whole recording</span><div class="controls">${P.kind === "record"
        ? `<a class="btn small" href="${esc(P.audio)}" target="_blank" rel="noopener" download>Audio (MP3)</a><a class="btn small" href="${esc(P.source)}" target="_blank" rel="noopener">${srcName(P)} page</a>`
        : `<button class="btn small" data-dl="mp3">Audio (MP3)</button><button class="btn small" data-dl="wav">Audio (WAV, lossless)</button><a class="btn small" href="${esc(P.midi)}" download="${esc(fileBase())}.mid">Roll (MIDI)</a>`}</div>
        ${P.kind === "record" ? "" : `<span class="pts">The audio is made in your browser from the roll, on the same piano as the game. It takes a little while for long pieces.</span>`}</div>
      <div class="controls"><button class="btn" id="full">▶ Keep listening (60s)</button>${daily ? "" : `<button class="btn primary" onclick="document.getElementById('newp').click()">Next puzzle</button>`}</div>
      ${daily ? `<div class="share">${esc(shareText())}</div><div class="controls"><button class="btn primary" id="copy">Copy result</button><a class="btn" href="#practice">Practice more</a></div>` : ""}
      <div class="stats"><div><b>${st.played}</b><span>Played</span></div><div><b>${st.played ? (st.total / st.played).toFixed(1) : "–"}</b><span>Avg score</span></div><div><b>${st.best}</b><span>Best</span></div></div>
    </section>`;
  }

  /* ---------- boot ---------- */
  fetch("data/catalog.json").then(r => r.json()).then(cat => {
    CAT = cat;
    fetch("data/clues.json").then(r => r.json()).then(c => { CAT.clues = c; }).catch(() => { CAT.clues = {}; });
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
    const route = () => (location.hash === "#changelog" ? renderChangelog() : location.hash === "#library" ? renderLibrary()
      : location.hash === "#score" || location.hash === "#score-practice" ? renderScore(location.hash === "#score-practice")
      : setMode(location.hash === "#practice" ? "practice" : "daily"));
    window.addEventListener("hashchange", route);
    window.addEventListener("resize", () => { const c = document.getElementById("roll"); if (c) draw(c, 0); });
    route();
  }).catch(e => {
    app.insertAdjacentHTML("beforeend", `<div class="panel"><h2>The recordings didn't load.</h2><p class="how">Check your connection and reload the page.</p></div>`);
    console.error(e);
  });
})();
