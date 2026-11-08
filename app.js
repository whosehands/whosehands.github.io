/* Whose Hands — a daily guessing game for historic recordings.
   Rolls: Stanford University Piano Roll Archive (CC BY-NC-SA 4.0).
   Records: Library of Congress National Jukebox (public domain in the US).
   Piano sound: Salamander Grand Piano by Alexander Holm (CC BY 3.0). Playback: Tone.js (MIT). */
(function () {
  "use strict";
  const SNIPS = [2, 4, 7, 11, 16, 24];
  const REPO = "concord-mass/concord-mass.github.io";
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

  let CAT, P, DAY, S;

  function dayIndex(epoch) {
    const [y, m, d] = epoch.split("-").map(Number);
    const e = new Date(y, m - 1, d), n = new Date();
    const t = new Date(n.getFullYear(), n.getMonth(), n.getDate());
    return Math.round((t - e) / 86400000);
  }
  function surname(n) { return norm(n).split(" ").pop(); }
  function pianistMatches(guess, answer) {
    const g = norm(guess); if (!g) return false;
    if (g === norm(answer)) return true;
    const sn = surname(answer);
    if (g === sn) {
      const clash = CAT.allPerformers.filter(p => surname(p) === sn && norm(p) !== norm(answer));
      return clash.length === 0;
    }
    return false;
  }
  function composerOf(pieceStr) { return norm(pieceStr.split(" – ")[0]); }

  /* ---------- scoring ---------- */
  const pianistPts = t => (t ? [0, 5, 4, 3, 2, 1, 1][t] : 0);
  const piecePts = t => (t ? (t <= 2 ? 3 : t <= 4 ? 2 : 1) : 0);
  function yearPts() {
    if (S.year == null) return 0;
    const lo = P.yearMin, hi = P.yearMax;
    const d = S.year < lo ? lo - S.year : S.year > hi ? S.year - hi : 0;
    return d <= 2 ? 2 : d <= 6 ? 1 : 0;
  }
  function pianistScore() {
    const per = 5 / P.performers.length;
    return P.performers.reduce((sum, p, i) => sum + (S.pianistAt[i] ? per * pianistPts(S.pianistAt[i]) / 5 : 0), 0);
  }
  function pieceScore() { return S.pieceAt ? piecePts(S.pieceAt) : (S.composerAt ? 1 : 0); }
  function total() { return Math.round((pianistScore() + pieceScore() + yearPts()) * 10) / 10; }
  const allPianists = () => P.performers.every((_, i) => S.pianistAt[i]);

  /* ---------- audio ---------- */
  const Audio = {
    sampler: null, notes: null, first: 0, loading: null, playing: false, raf: 0,
    samplerLoading: null,
    loadSampler() {
      if (this.samplerLoading) return this.samplerLoading;
      this.samplerLoading = (async () => {
        const urls = {};
        const names = { A: "A", C: "C", Ds: "D#", Fs: "F#" };
        for (let o = 0; o <= 8; o++) for (const k of Object.keys(names)) {
          const note = names[k] + o;
          if ((o === 0 && k !== "A") || (o === 8 && k !== "C")) continue;
          urls[note] = k + o + ".mp3";
        }
        await new Promise((res, rej) => {
          this.sampler = new Tone.Sampler({ urls, baseUrl: "samples/", release: 1, onload: res, onerror: rej }).toDestination();
        });
      })();
      return this.samplerLoading;
    },
    async init() {
      if (this.loading) return this.loading;
      if (P.kind === "record") return (this.loading = Promise.resolve());
      this.loading = (async () => {
        const buf = await (await fetch(P.midi)).arrayBuffer();
        const midi = new Midi(buf);
        const pedal = [], soft = [];
        midi.tracks.forEach(t => {
          (t.controlChanges[64] || []).forEach(c => pedal.push([c.time, c.value >= 0.5]));
          (t.controlChanges[67] || []).forEach(c => soft.push([c.time, c.value >= 0.5]));
        });
        pedal.sort((a, b) => a[0] - b[0]); soft.sort((a, b) => a[0] - b[0]);
        const stateAt = (list, t) => { let s = false; for (const [ti, v] of list) { if (ti > t) break; s = v; } return s; };
        const nextUp = (t) => { for (const [ti, v] of pedal) if (ti > t && !v) return ti; return t + 4; };
        const notes = [];
        midi.tracks.forEach(t => t.notes.forEach(n => {
          let end = n.time + n.duration;
          if (stateAt(pedal, end)) end = Math.max(end, nextUp(end));
          let v = Math.min(1, n.velocity * 1.55);
          if (stateAt(soft, n.time)) v *= 0.8;
          notes.push({ name: n.name, midi: n.midi, time: n.time, dur: Math.max(0.05, end - n.time), vel: v });
        }));
        notes.sort((a, b) => a.time - b.time);
        this.notes = notes; this.first = notes.length ? notes[0].time : 0;
      })();
      return this.loading;
    },
    el: null,
    async playRecord(secs, onTick, onEnd) {
      this.stop();
      if (!this.el) { this.el = new window.Audio(); this.el.preload = "auto"; this.el.src = P.audio; }
      const a = this.el, start = P.start || 0;
      await new Promise((res, rej) => {
        if (a.readyState >= 1) return res();
        a.addEventListener("loadedmetadata", res, { once: true }); a.addEventListener("error", () => rej(new Error("audio")), { once: true });
      });
      a.currentTime = start; await a.play();
      this.playing = true;
      const loop = () => {
        if (!this.playing) return;
        const el = a.currentTime - start;
        onTick && onTick(Math.min(el, secs), 0);
        if (el >= secs || a.ended) { this.stop(onEnd); return; }
        this.raf = requestAnimationFrame(loop);
      };
      loop();
    },
    async play(secs, onTick, onEnd) {
      if (P.kind === "record") return this.playRecord(secs, onTick, onEnd);
      const started = Tone.start();
      await Promise.all([started, this.init(), this.loadSampler()]);
      this.stop();
      const T = Tone.Transport;
      const t0 = this.first;
      this.notes.forEach(n => {
        if (n.time - t0 > secs) return;
        const dur = Math.min(n.dur, secs - (n.time - t0) + 0.6);
        T.schedule(time => this.sampler.triggerAttackRelease(n.name, dur, time, n.vel), n.time - t0);
      });
      T.schedule(() => { Tone.Draw.schedule(() => this.stop(onEnd), Tone.now()); }, secs + 0.8);
      T.start("+0.05");
      this.playing = true;
      const loop = () => { if (!this.playing) return; onTick && onTick(Math.min(T.seconds, secs), t0); this.raf = requestAnimationFrame(loop); };
      loop();
    },
    stop(onEnd) {
      if (this.el) this.el.pause();
      const T = Tone.Transport;
      T.stop(); T.cancel(0);
      if (this.sampler) this.sampler.releaseAll();
      cancelAnimationFrame(this.raf);
      const was = this.playing; this.playing = false;
      if (was && onEnd) onEnd();
    }
  };

  /* ---------- roll drawing ---------- */
  function drawRoll(canvas, at, t0) {
    const dpr = window.devicePixelRatio || 1, w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== w * dpr) { canvas.width = w * dpr; canvas.height = h * dpr; }
    const g = canvas.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const css = getComputedStyle(document.documentElement);
    if (P.kind === "record") { drawDisc(g, w, h, at || 0, css); return; }
    g.fillStyle = css.getPropertyValue("--roll").trim(); g.fillRect(0, 0, w, h);
    g.fillStyle = css.getPropertyValue("--hole").trim();
    const span = 3.2, px = h / span;
    if (!Audio.notes) return;
    const now = t0 + (at || 0);
    for (const n of Audio.notes) {
      if (n.time > now + span) break;
      if (n.time + Math.min(n.dur, 1.2) < now - 0.2) continue;
      const x = ((n.midi - 21) / 88) * (w - 16) + 8;
      const y = h - (n.time - now) * px - 18;
      g.fillRect(x, y - Math.min(n.dur, 1.2) * px * 0.35, Math.max(2, w / 160), Math.max(3, Math.min(n.dur, 1.2) * px * 0.35));
    }
    g.fillStyle = "rgba(255,255,255,.35)"; g.fillRect(0, h - 18, w, 1);
  }

  function drawDisc(g, w, h, at, css) {
    g.fillStyle = css.getPropertyValue("--roll").trim(); g.fillRect(0, 0, w, h);
    const cx = w / 2, cy = h / 2, R = h * 0.46;
    g.fillStyle = "#121214"; g.beginPath(); g.arc(cx, cy, R, 0, Math.PI * 2); g.fill();
    g.strokeStyle = "rgba(255,255,255,.07)"; g.lineWidth = 1;
    for (let r = R * 0.42; r < R - 2; r += 2.5) { g.beginPath(); g.arc(cx, cy, r, 0, Math.PI * 2); g.stroke(); }
    const ang = at * 78 / 60 * Math.PI * 2;
    g.strokeStyle = "rgba(255,255,255,.18)"; g.lineWidth = R * 0.5;
    g.beginPath(); g.arc(cx, cy, R * 0.7, ang, ang + 0.35); g.stroke();
    g.fillStyle = css.getPropertyValue("--roll").trim(); g.beginPath(); g.arc(cx, cy, R * 0.36, 0, Math.PI * 2); g.fill();
    g.fillStyle = css.getPropertyValue("--hole").trim(); g.beginPath(); g.arc(cx, cy, 3, 0, Math.PI * 2); g.fill();
  }

  /* ---------- state ---------- */
  function load() {
    const s = store.get("wh2-day-" + DAY, null);
    return s && s.id === P.id ? s : { id: P.id, tries: [], pianistAt: P.performers.map(() => 0), pieceAt: 0, composerAt: 0, year: null, done: false };
  }
  const save = () => store.set("wh2-day-" + DAY, S);
  function recordStats() {
    const st = store.get("wh2-stats", { played: 0, total: 0, best: 0, days: {} });
    if (st.days[DAY] !== undefined) return;
    const pts = total(); st.days[DAY] = pts; st.played++; st.total += pts; st.best = Math.max(st.best, pts);
    store.set("wh2-stats", st);
  }

  const roleOf = i => (P.roles && P.roles[i]) || "piano";
  function roleLabel(i) {
    const r = roleOf(i);
    if (r === "piano") return P.performers.length > 1 ? "Pianist " + (i + 1) : "Pianist";
    return r.charAt(0).toUpperCase() + r.slice(1);
  }
  function hintsFor() {
    const h = [];
    if (P.kind === "record") h.push(`${P.label || "A"} record${P.place ? ", recorded in " + P.place : ""}`);
    else h.push(P.place ? `Roll recorded in ${P.place}` : `Recorded on a ${P.format}`);
    h.push(`Composer: ${P.composer}${P.composerDates ? " (" + P.composerDates + ")" : ""}`);
    const d = P.performerDates[P.performers[0]];
    const who = P.kind === "record" ? `The ${roleOf(0) === "orchestra" ? "orchestra" : roleLabel(0).toLowerCase()}` : "The pianist";
    const cnt = CAT.countBy[P.performers[0]] || 1;
    h.push(d ? `${who} lived ${d}` : `${who} appears in ${cnt} puzzle${cnt > 1 ? "s" : ""} in this game`);
    const sn = P.performers[0].split(" ").pop();
    h.push(`${who}'s name ends in a ${sn.replace(/[^\p{L}]/gu, "").length}-letter word`);
    h.push(`${who}'s last name starts with “${sn.replace(/^(d'|de |von |van )/i, "")[0]}”`);
    return h;
  }

  /* ---------- render ---------- */
  function render() {
    const used = S.tries.length;
    const unlocked = S.done ? SNIPS.length : Math.min(used + 1, SNIPS.length);
    const secs = SNIPS[unlocked - 1];
    const hints = hintsFor().slice(0, Math.min(used, 5));
    const dateStr = new Date().toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
    const multi = P.performers.length > 1;

    app.innerHTML = `
    <header><h1>Whose <em>Hands</em></h1><span class="meta">No. ${DAY + 1} · ${esc(dateStr)}</span></header>
    ${used === 0 && !S.done ? (P.kind === "record"
      ? `<p class="how">Today's recording was made on a 78 record between 1900 and 1925. Guess everyone featured on it, the piece, and the year. Each miss plays more and adds a hint.</p>`
      : `<p class="how">A legendary pianist recorded today's piece on a piano roll between 1905 and 1925. You hear their exact notes, pedaling and timing on a modern piano. Guess who, what, and when. Each miss plays more and adds a hint.</p>`) : ""}

    <section class="player" aria-label="Today's roll">
      <div class="rollbox"><canvas id="roll" aria-hidden="true"></canvas><span class="tag">${P.kind === "record" ? "78 RPM" : "WELTE-MIGNON"} · NO. ${DAY + 1}</span><span class="status" id="status"></span></div>
      <div class="controls">
        <button class="btn primary" id="play">▶ Play ${secs}s</button>
        <button class="btn" id="stop">Stop</button>
      </div>
      <div><div class="bar">${SNIPS.map((v, i) => `<span class="${i < unlocked ? "open" : ""}" style="flex:${v - (i ? SNIPS[i - 1] : 0)}"><i></i></span>`).join("")}</div>
      <div class="legend"><span>0s</span><span>${SNIPS[SNIPS.length - 1]}s</span></div></div>
    </section>

    <section class="panel">
      <div class="row"><h2>${P.kind === "record" ? "Who's on it, and what?" : "Who's playing, and what?"}</h2><span class="pts">${used}/${SNIPS.length} tries</span></div>
      ${S.done ? "" : `<form id="guess" autocomplete="off">
        ${P.performers.map((p, i) => `<div class="field ${S.pianistAt[i] ? "solved" : ""}"><div class="row"><label class="label" for="g-p${i}">${esc(roleLabel(i))}</label>${S.pianistAt[i] ? `<span class="chip">✓</span>` : `<span class="pts">up to ${Math.round(50 / P.performers.length) / 10} pts</span>`}</div>
          <input type="text" id="g-p${i}" list="dl-pianists" placeholder="${roleOf(i) === "orchestra" ? "Start typing an orchestra" : "Start typing a name"}" ${S.pianistAt[i] ? `value="${esc(p)}" disabled` : ""}></div>`).join("")}
        <div class="field ${S.pieceAt ? "solved" : ""}"><div class="row"><label class="label" for="g-piece">Piece</label>${S.pieceAt ? `<span class="chip">✓</span>` : S.composerAt ? `<span class="chip part">Composer ✓</span>` : `<span class="pts">up to 3 pts · right composer 1</span>`}</div>
          <input type="text" id="g-piece" list="dl-pieces" placeholder="Start typing a composer or title" ${S.pieceAt ? `value="${esc(P.piece)}" disabled` : ""}></div>
        <div class="controls"><button class="btn primary" type="submit">Guess</button><button class="btn" type="button" id="skip">Skip, play more</button></div>
      </form>`}
      ${hints.length ? `<div><div class="label">Hints</div><ul class="hints">${hints.map(h => `<li>${esc(h)}</li>`).join("")}</ul></div>` : ""}
      ${used ? `<ul class="tries">${S.tries.map((t, i) => `<li><span class="n">${i + 1}</span><span class="g">${t.p.map(x => `<span class="${x.ok ? "ok" : "no"}">${esc(x.g || "—")}</span>`).join(" · ")}<br><span class="${t.piece.ok ? "ok" : t.piece.comp ? "part" : "no"}">${esc(t.piece.g || "—")}</span></span></li>`).join("")}</ul>` : ""}
    </section>

    <section class="panel">
      <div class="row"><h2>When was it recorded?</h2><span class="pts">2 pts within 2 years · 1 pt within 6</span></div>
      <div class="year">
        <div class="row"><span class="val" id="yv">${S.year ?? 1912}</span>${S.year != null ? `<span class="chip">Locked in</span>` : ""}</div>
        <input type="range" id="year" min="1900" max="1930" step="1" value="${S.year ?? 1912}" ${S.year != null ? "disabled" : ""} aria-label="Recording year">
        ${S.year == null ? `<div class="controls"><button class="btn" id="lockyear">Lock in year</button></div>` : ""}
      </div>
    </section>

    ${S.done ? resultHTML() : ""}

    <footer>
      <span>A new roll every day at midnight. Rolls from the <a href="https://supra.stanford.edu" target="_blank" rel="noopener">Stanford University Piano Roll Archive</a> (CC BY-NC-SA 4.0). Records from the <a href="https://www.loc.gov/collections/national-jukebox/" target="_blank" rel="noopener">Library of Congress National Jukebox</a> (public domain). Piano sound: Salamander Grand Piano by Alexander Holm (CC BY 3.0). Played with Tone.js.</span>
      <span>Something wrong with today's answer? <a href="https://github.com/${REPO}/issues/new?title=${encodeURIComponent("Problem with roll No. " + (DAY + 1))}&body=${encodeURIComponent("Roll id: " + P.id + "\nWhat's wrong:\n")}" target="_blank" rel="noopener">Report it</a>.</span>
    </footer>
    <datalist id="dl-pianists">${CAT.pianistOptions.map(p => `<option value="${esc(p)}">`).join("")}</datalist>
    <datalist id="dl-pieces">${CAT.pieceOptions.map(p => `<option value="${esc(p)}">`).join("")}</datalist>`;

    const canvas = document.getElementById("roll"), status = document.getElementById("status");
    drawRoll(canvas, 0, Audio.first);
    const bars = [...app.querySelectorAll(".bar span i")];
    const tick = (el) => {
      drawRoll(canvas, el, Audio.first);
      let acc = 0; bars.forEach((b, i) => { const len = SNIPS[i] - (i ? SNIPS[i - 1] : 0); b.style.width = Math.max(0, Math.min(1, (el - acc) / len)) * 100 + "%"; acc += len; });
    };
    document.getElementById("play").onclick = async () => {
      status.textContent = Audio.notes ? "PLAYING" : "LOADING PIANO…";
      try { await Audio.play(secs, tick, () => { status.textContent = ""; }); status.textContent = "PLAYING"; }
      catch (e) { status.textContent = "COULDN'T LOAD AUDIO"; console.error(e); }
    };
    document.getElementById("stop").onclick = () => { Audio.stop(); status.textContent = ""; };

    const yr = document.getElementById("year"), yv = document.getElementById("yv");
    yr.oninput = () => { yv.textContent = yr.value; };
    const ly = document.getElementById("lockyear");
    if (ly) ly.onclick = () => { S.year = +yr.value; save(); if (S.done) recordStats(); render(); };

    const form = document.getElementById("guess");
    if (form) {
      const submit = (skip) => {
        const n = S.tries.length + 1;
        const pg = P.performers.map((_, i) => skip ? "" : (document.getElementById("g-p" + i)?.value || ""));
        const pcg = skip ? "" : (document.getElementById("g-piece")?.value || "");
        if (!skip && !pg.some(x => x.trim()) && !pcg.trim()) return;
        const tryRec = { p: [], piece: {} };
        P.performers.forEach((_, i) => {
          if (S.pianistAt[i]) { tryRec.p.push({ g: "", ok: true }); return; }
          const j = P.performers.findIndex((ans, k) => !S.pianistAt[k] && pianistMatches(pg[i], ans));
          if (j >= 0) S.pianistAt[j] = n;
          tryRec.p.push({ g: skip ? "(skipped)" : pg[i], ok: j >= 0 });
        });
        if (S.pieceAt) tryRec.piece = { g: "", ok: true };
        else {
          const ok = norm(pcg) === norm(P.piece);
          const comp = !ok && pcg && composerOf(pcg) === composerOf(P.piece);
          if (ok) S.pieceAt = n;
          if (comp && !S.composerAt) S.composerAt = n;
          tryRec.piece = { g: skip ? "(skipped)" : pcg, ok, comp };
        }
        S.tries.push(tryRec);
        if ((allPianists() && S.pieceAt) || n >= SNIPS.length) { S.done = true; if (S.year != null) recordStats(); }
        save(); Audio.stop(); render();
      };
      form.onsubmit = e => { e.preventDefault(); submit(false); };
      document.getElementById("skip").onclick = () => submit(true);
    }
    const copy = document.getElementById("copy");
    if (copy) copy.onclick = async () => {
      const txt = document.querySelector(".share").textContent;
      try { await navigator.clipboard.writeText(txt); copy.textContent = "Copied"; }
      catch (e) { const r = document.createRange(); r.selectNodeContents(document.querySelector(".share")); const s = getSelection(); s.removeAllRanges(); s.addRange(r); copy.textContent = "Selected, now copy"; }
    };
  }

  function shareText() {
    const rows = S.tries.map((t, i) => {
      const n = i + 1;
      if (S.pianistAt.some(a => a === n)) return "🟩";
      if (S.pieceAt === n || S.composerAt === n) return "🟨";
      return "⬛";
    }).join("");
    return `Whose Hands No. ${DAY + 1} · ${total()}/10\n${P.kind === "record" ? "Performers" : "Pianist"} ${allPianists() ? "✅" : "❌"}  Piece ${S.pieceAt ? "✅" : S.composerAt ? "🟨" : "❌"}  Year ${yearPts() === 2 ? "✅" : yearPts() === 1 ? "🟨" : "❌"}\n${rows}\nhttps://concord-mass.github.io`;
  }
  function resultHTML() {
    if (S.year == null) return `<section class="panel result"><h2>Last step: lock in your year above to see the answer.</h2></section>`;
    const st = store.get("wh2-stats", { played: 0, total: 0, best: 0 });
    const yr = P.yearMin === P.yearMax ? P.yearMin : `${P.yearMin}–${P.yearMax}`;
    return `<section class="panel result">
      <div class="row"><h2>${allPianists() ? "You knew those hands." : "Today's hands"}</h2><span class="label">Result</span></div>
      <div class="score">${total()}<small> / 10</small></div>
      <dl class="answer">
        <dt>${P.performers.length > 1 ? "Performers" : roleLabel(0)}</dt><dd><b>${P.performers.map((p, i) => esc(p) + (P.performers.length > 1 ? ` <span class="pts">${esc(roleOf(i))}</span>` : "") + (P.performerDates[p] ? ` <span class="pts">(${esc(P.performerDates[p])})</span>` : "")).join("<br>")}</b></dd>
        <dt>Piece</dt><dd>${esc(P.piece)}${P.rollLabel ? `<br><span class="pts">${P.kind === "record" ? "Record label" : "Roll label"}: ${esc(P.rollLabel)}</span>` : ""}</dd>
        <dt>Recorded</dt><dd>${esc(String(yr))}${P.yearExact ? "" : " (published; exact date unknown)"}</dd>
        <dt>Your year</dt><dd>${S.year} · ${yearPts()} pt${yearPts() === 1 ? "" : "s"}</dd>
        <dt>Source</dt><dd>${esc(P.format)}${P.rollNumber ? " no. " + esc(P.rollNumber) : ""} · <a href="${esc(P.source)}" target="_blank" rel="noopener">${P.kind === "record" ? "Library of Congress" : "Stanford"} record</a></dd>
      </dl>
      <div class="controls"><button class="btn" id="full">▶ Hear 60 seconds</button></div>
      <div class="share">${esc(shareText())}</div>
      <div class="controls"><button class="btn primary" id="copy">Copy result</button></div>
      <div class="stats"><div><b>${st.played}</b><span>Played</span></div><div><b>${st.played ? (st.total / st.played).toFixed(1) : "–"}</b><span>Avg score</span></div><div><b>${st.best}</b><span>Best</span></div></div>
    </section>`;
  }

  /* ---------- boot ---------- */
  fetch("data/catalog.json").then(r => r.json()).then(cat => {
    CAT = cat;
    const byId = Object.fromEntries(cat.recordings.map(r => [r.id, r]));
    DAY = Math.max(0, dayIndex(cat.epoch));
    P = byId[cat.schedule[DAY % cat.schedule.length]];
    CAT.allPerformers = [...new Set(cat.recordings.flatMap(r => r.performers))];
    CAT.countBy = {}; cat.recordings.forEach(r => r.performers.forEach(p => CAT.countBy[p] = (CAT.countBy[p] || 0) + 1));
    CAT.pianistOptions = [...new Set(CAT.allPerformers.concat(DECOYS))].sort((a, b) => surname(a).localeCompare(surname(b)));
    CAT.pieceOptions = [...new Set(cat.recordings.map(r => r.piece))].sort();
    S = load();
    render();
    Audio.init().then(() => { const c = document.getElementById("roll"); if (c) drawRoll(c, 0, Audio.first); }).catch(() => {});
    document.addEventListener("click", e => {
      if (e.target && e.target.id === "full") {
        const st = document.getElementById("status"); if (st) st.textContent = "PLAYING";
        Audio.play(60, el => { const c = document.getElementById("roll"); if (c) drawRoll(c, el, Audio.first); }, () => { const s2 = document.getElementById("status"); if (s2) s2.textContent = ""; });
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    });
    window.addEventListener("resize", () => { const c = document.getElementById("roll"); if (c) drawRoll(c, 0, Audio.first); });
  }).catch(e => {
    app.insertAdjacentHTML("beforeend", `<div class="panel"><h2>Today's roll didn't load.</h2><p class="how">Check your connection and reload the page.</p></div>`);
    console.error(e);
  });
})();
