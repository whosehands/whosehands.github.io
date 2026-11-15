/* Whose Hands piano: plays piano-roll notes with the Salamander Grand Piano V3 samples (Alexander Holm, CC BY 3.0).
   Seven velocity layers sampled every minor third, key-release noise, pedal noise, damper behaviour and a small room reverb.
   The same code plays clips in the game and renders whole rolls for download. */
(function () {
  "use strict";
  const LAYERS = [2, 5, 7, 9, 11, 13, 15];                 // Salamander velocity layers we ship
  const LAYER_VEL = [30, 45, 53, 68, 84, 100, 116];         // the MIDI velocity each layer was recorded at (middle of its range)
  const NAMES = ["A", "C", "Ds", "Fs"];
  // sample i is pitched at MIDI 21 + 3i: A0, C1, D#1, F#1, A1 ... C8
  const sampleName = i => { const m = 21 + 3 * i; return NAMES[i % 4] + (Math.floor(m / 12) - 1); };
  const BASE = "piano/";
  const buffers = {};                                      // "C4v9" -> AudioBuffer
  const loading = {};

  const load = (ctx, name) => (loading[name] = loading[name] || fetch(BASE + name + ".mp3").then(r => { if (!r.ok) throw new Error(name); return r.arrayBuffer(); })
    .then(b => new Promise((res, rej) => ctx.decodeAudioData(b, res, rej))).then(buf => (buffers[name] = buf)));
  function loadLayer(ctx, L) { const jobs = []; for (let i = 0; i < 30; i++) jobs.push(load(ctx, sampleName(i) + "v" + L)); return Promise.all(jobs); }
  function loadExtras(ctx) { const jobs = ["pedalD1", "pedalD2", "pedalU1", "pedalU2"].map(n => load(ctx, n)); for (let k = 1; k <= 88; k++) jobs.push(load(ctx, "rel" + k)); return Promise.all(jobs); }
  const layerReady = L => !!buffers["C4v" + L] && Array.from({ length: 30 }, (_, i) => buffers[sampleName(i) + "v" + L]).every(Boolean);
  async function loadAll(ctx, onProgress) {      // the middle layer first so playing can start; the rest after
    await loadLayer(ctx, 9);
    const rest = [7, 11, 5, 13, 2, 15].map(L => loadLayer(ctx, L));
    let done = 1; rest.forEach(p => p.then(() => onProgress && onProgress(++done / 7)));
    return Promise.all([...rest, loadExtras(ctx)]);
  }

  /* Turn roll MIDI (parsed by @tonejs/midi) into notes with damper and pedal timing. */
  function prepare(midi) {
    const pedal = [], soft = [];
    midi.tracks.forEach(t => {
      (t.controlChanges[64] || []).forEach(c => pedal.push([c.time, c.value >= 0.5]));
      (t.controlChanges[67] || []).forEach(c => soft.push([c.time, c.value >= 0.5]));
    });
    pedal.sort((a, b) => a[0] - b[0]); soft.sort((a, b) => a[0] - b[0]);
    const stateAt = (list, t) => { let lo = 0, hi = list.length - 1, s = false; while (lo <= hi) { const m = (lo + hi) >> 1; if (list[m][0] <= t) { s = list[m][1]; lo = m + 1; } else hi = m - 1; } return s; };
    const nextUp = t => { for (const [ti, v] of pedal) if (ti > t && !v) return ti; return t + 4; };
    const notes = [];
    midi.tracks.forEach(t => t.notes.forEach(n => {
      const keyUp = n.time + n.duration, held = stateAt(pedal, keyUp);
      const raw = n.velocity * 127;                         // roll velocities run from about 32 (pp) to 87 (ff)
      let vel = Math.max(12, Math.min(127, 20 + (raw - 32) * 1.7));
      if (stateAt(soft, n.time)) vel *= 0.82;               // una corda
      notes.push({ name: n.name, midi: n.midi, time: n.time, keyUp, off: held ? Math.max(keyUp, nextUp(keyUp)) : keyUp, dampedByKey: !held, vel });
    }));
    notes.sort((a, b) => a.time - b.time);
    const last = {};
    for (const n of notes) {                                // striking a key again cuts off its earlier note
      const p = last[n.midi];
      if (p && p.off > n.time) { p.off = n.time; p.restruck = true; }
      last[n.midi] = n;
    }
    const pedalMoves = [];
    let prev = false;
    for (const [t, v] of pedal) { if (v !== prev) pedalMoves.push([t, v]); prev = v; }
    return { notes, pedalMoves, dur: notes.length ? Math.max(...notes.slice(-200).map(n => n.off)) + 2 : 0 };
  }

  /* Effects: a small hall made from a seeded noise impulse, plus a gentle limiter. */
  function chain(ctx, out) {
    const input = ctx.createGain(), dry = ctx.createGain(), wet = ctx.createGain(), comp = ctx.createDynamicsCompressor(), master = ctx.createGain();
    const len = Math.round(ctx.sampleRate * 2.4), ir = ctx.createBuffer(2, len, ctx.sampleRate);
    let seed = 7;
    const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647 * 2 - 1; };
    for (let c = 0; c < 2; c++) { const d = ir.getChannelData(c); for (let i = 0; i < len; i++) { const t = i / ctx.sampleRate; d[i] = t < 0.012 ? 0 : rnd() * Math.exp(-t * 2.9) * (1 - Math.exp(-t * 60)); } }
    const conv = ctx.createConvolver(); conv.normalize = true; conv.buffer = ir;
    const tone = ctx.createBiquadFilter(); tone.type = "lowpass"; tone.frequency.value = 5200;
    dry.gain.value = 0.86; wet.gain.value = 0.26;
    comp.threshold.value = -10; comp.knee.value = 8; comp.ratio.value = 3; comp.attack.value = 0.004; comp.release.value = 0.25;
    master.gain.value = 0.9;
    input.connect(dry); input.connect(tone); tone.connect(conv); conv.connect(wet);
    dry.connect(comp); wet.connect(comp); comp.connect(master); master.connect(out);
    return { input, master };
  }

  function pickLayer(vel) {
    let best = -1, bd = 1e9;
    LAYER_VEL.forEach((v, i) => { const d = Math.abs(v - vel); if (d < bd && layerReady(LAYERS[i])) { bd = d; best = i; } });
    if (best < 0) return null;
    return { L: LAYERS[best], gain: Math.pow(vel / LAYER_VEL[best], 0.9) };
  }

  /* Schedule notes that start in [from, to) on ctx. Song time `origin` plays at ctx time `at`.
     Notes that began before `origin` (used when rendering in pieces) start part-way through their sample.
     `cut` (song time) silences everything shortly after a clip ends. */
  function schedule(ctx, dest, song, { from, to, origin = from, at, cut = Infinity, extras = true }) {
    const sources = [];
    const play = (buf, when, gainVal, rate, startSec, offAt, tau) => {
      const src = ctx.createBufferSource(); src.buffer = buf; src.playbackRate.value = rate;
      const g = ctx.createGain();
      let t = at + (when - origin), off = 0;
      if (t < at) { off = (at - t) * rate; t = at; }
      if (off >= buf.duration) return;
      const remainOff = at + (offAt - origin);
      let g0 = gainVal;
      if (remainOff < t) { g0 = gainVal * Math.exp(-(t - remainOff) / tau); if (g0 < 1e-4) return; }
      g.gain.setValueAtTime(g0, t);
      if (remainOff >= t) g.gain.setTargetAtTime(0, remainOff, tau); else g.gain.setTargetAtTime(0, t, tau);
      src.connect(g); g.connect(dest);
      src.start(t, off);
      src.stop(Math.max(t, (remainOff >= t ? remainOff : t)) + tau * 7);
      sources.push(src);
    };
    for (const n of song.notes) {
      if (n.time >= to) break;
      if (n.time < from || n.time < origin - 12.5) continue;
      const lay = pickLayer(n.vel); if (!lay) continue;
      const i = Math.max(0, Math.min(29, Math.round((n.midi - 21) / 3))), buf = buffers[sampleName(i) + "v" + lay.L];
      if (!buf) continue;
      const rate = Math.pow(2, (n.midi - (21 + 3 * i)) / 12);
      const undamped = n.midi >= 89;                        // the top strings have no dampers
      let offAt = undamped ? n.time + buf.duration : n.off, tau = n.restruck ? 0.03 : undamped ? 0.9 : 0.09 + 0.22 * Math.max(0, (88 - n.midi) / 67);
      if (offAt > cut) { offAt = cut; tau = Math.min(tau, 0.25); }
      play(buf, n.time, 0.6 * lay.gain, rate, 0, offAt, tau);
      if (extras && n.dampedByKey && !undamped && n.keyUp < cut && n.keyUp >= origin) {   // the damper falling back onto the string
        const rb = buffers["rel" + (n.midi - 20)];
        if (rb) play(rb, n.keyUp, 0.012 * (0.4 + n.vel / 127), 1, 0, n.keyUp + 5, 1);
      }
    }
    if (extras) for (const [t, down] of song.pedalMoves) {
      if (t < Math.max(from, origin - 1) || t >= to || t > cut) continue;
      const b = buffers[(down ? "pedalD" : "pedalU") + (1 + (Math.floor(t * 10) % 2))];
      if (b) play(b, t, down ? 0.05 : 0.06, 1, 0, t + 10, 1);
    }
    return sources;
  }

  /* ---------- whole-roll rendering for downloads ---------- */
  async function renderChunks(song, sampleRate, onChunk, onProgress) {
    const CH = 30, PRE = 4, total = song.dur;
    for (let a = 0; a < total; a += CH) {
      const b = Math.min(total, a + CH), origin = Math.max(0, a - PRE), len = b - origin;
      const ctx = new OfflineAudioContext(2, Math.ceil(len * sampleRate), sampleRate);
      const fx = chain(ctx, ctx.destination);
      schedule(ctx, fx.input, song, { from: 0, to: b, origin, at: 0 });
      const buf = await ctx.startRendering();
      const skip = Math.round((a - origin) * sampleRate);
      onChunk(buf.getChannelData(0).subarray(skip), buf.getChannelData(1).subarray(skip));
      onProgress && onProgress(b / total);
      await new Promise(r => setTimeout(r, 0));
    }
  }
  const toI16 = f => { const o = new Int16Array(f.length); for (let i = 0; i < f.length; i++) { const s = Math.max(-1, Math.min(1, f[i])); o[i] = s < 0 ? s * 32768 : s * 32767; } return o; };
  async function renderMp3(song, onProgress) {
    const rate = 44100, enc = new lamejs.Mp3Encoder(2, rate, 192), parts = [];
    await renderChunks(song, rate, (l, r) => {
      const L = toI16(l), R = toI16(r);
      for (let i = 0; i < L.length; i += 1152) { const m = enc.encodeBuffer(L.subarray(i, i + 1152), R.subarray(i, i + 1152)); if (m.length) parts.push(new Uint8Array(m)); }
    }, onProgress);
    const end = enc.flush(); if (end.length) parts.push(new Uint8Array(end));
    return new Blob(parts, { type: "audio/mpeg" });
  }
  async function renderWav(song, onProgress) {
    const rate = 44100, parts = []; let frames = 0;
    await renderChunks(song, rate, (l, r) => {
      const L = toI16(l), R = toI16(r), out = new Int16Array(L.length * 2);
      for (let i = 0; i < L.length; i++) { out[2 * i] = L[i]; out[2 * i + 1] = R[i]; }
      parts.push(out); frames += L.length;
    }, onProgress);
    const h = new DataView(new ArrayBuffer(44)), w = (o, s) => [...s].forEach((c, i) => h.setUint8(o + i, c.charCodeAt(0)));
    w(0, "RIFF"); h.setUint32(4, 36 + frames * 4, true); w(8, "WAVE"); w(12, "fmt "); h.setUint32(16, 16, true); h.setUint16(20, 1, true); h.setUint16(22, 2, true);
    h.setUint32(24, rate, true); h.setUint32(28, rate * 4, true); h.setUint16(32, 4, true); h.setUint16(34, 16, true); w(36, "data"); h.setUint32(40, frames * 4, true);
    return new Blob([h, ...parts], { type: "audio/wav" });
  }

  window.Piano = { loadAll, loadLayer, layerReady, prepare, chain, schedule, renderMp3, renderWav, buffers };
})();
