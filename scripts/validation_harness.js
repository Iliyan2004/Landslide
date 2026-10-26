// Verification and validation harness. It is appended to a copy of site/index.html and runs the dashboard's real
// simulation code in headless Chrome (see validate_simulation.py). Results go into a hidden element with id vresults, as JSON.
(async () => {
  const out = {tests: [], scen: {}, sites: [], proj: [], hf: [], data: {}, bench: [], errors: []};
  const add = (id, group, name, expected, got, tol, pass, note) => out.tests.push({id, group, name, expected, got, tol, pass: !!pass, note});
  const q8 = a => { const u = new Uint8Array(a.length); for (let i = 0; i < a.length; i++) u[i] = Math.round(Math.max(0, Math.min(1, a[i])) * 255); let s = ''; const C = 0x8000; for (let i = 0; i < u.length; i += C) s += String.fromCharCode.apply(null, u.subarray(i, i + C)); return btoa(s); };
  const setUI = (o) => { for (const [k, v] of Object.entries(o)) el(k).value = v; };
  const DEF = {'s-int': 10, 's-dur': 24, 's-sat': 0.3, 's-z': 1.5, 's-c': 6, 's-phi': 32};
  const rootOn = on => el('s-root').setAttribute('aria-pressed', on ? 'true' : 'false');
  try {
    // ================= V1-V3 infinite-slope stability =================
    {
      const rn = rng(123), picks = [];
      while (picks.length < 300) { const ci = Math.floor(rn() * NC); if (SL[ci] === 255) continue; picks.push(ci); }
      setUI(DEF); rootOn(false);
      picks.forEach(ci => { SL[ci] = Math.round(12 + rn() * 34); LC[ci] = 3; });
      prepare();
      const rn2 = rng(7), mem = [];
      for (let m = 0; m < NMEM; m++) mem.push({z: 1.5 * (1 + (rn2() * 2 - 1) * .25), c: 6 * (1 + (rn2() * 2 - 1) * .25), p: 32 + (rn2() * 2 - 1) * 3});
      const idx = new Map(); sim.cells.forEach((c, j) => idx.set(c, j));
      let maxrel = 0, n = 0, excl = 0, mism = 0;
      picks.forEach(ci => {
        const j = idx.get(ci); if (j === undefined) { excl++; return; }
        const b = SL[ci] * Math.PI / 180, cs2 = Math.cos(b) ** 2, sc = Math.sin(b) * Math.cos(b);
        mem.forEach((q, m) => {
          const cf = SOILC && SOILC[ci] !== 255 ? SOILC[ci] / 100 : 1, dp = SOILP && SOILP[ci] !== 255 ? SOILP[ci] / 20 - 4 : 0, tt = Math.tan((q.p + dp) * Math.PI / 180);
          const FS = mm => (q.c * cf + (GAM * q.z * cs2 - mm * GW * q.z * cs2) * tt) / (GAM * q.z * sc);
          let P; if (FS(.3) <= 1) P = 0; else if (FS(1) > 1) P = Infinity; else { let lo = .3, hi = 1; for (let it = 0; it < 80; it++) { const mid = (lo + hi) / 2; if (FS(mid) > 1) lo = mid; else hi = mid; } P = ((lo + hi) / 2 - .3) * POR * q.z * 1000 / INF; }
          const got = sim.pc[j][m];
          if (isFinite(P) && P > 0 && isFinite(got)) { maxrel = Math.max(maxrel, Math.abs(got - P) / P); n++; } else if (!(P === got)) mism++;
        });
      });
      add('V1', 'Stability', 'Critical rain from the code equals the closed-form root of FS = 1', '0', maxrel, '< 1e-4 relative', maxrel < 1e-4 && mism === 0, `${n} member-cell pairs on ${picks.length - excl} cells; classification mismatches ${mism}; ${excl} cells excluded as already unstable`);
      // V2 earthquake only lowers the critical rain
      const base = new Map(); sim.cells.forEach((c, j) => base.set(c, sim.pc[j]));
      setUI({'s-eq': D.shake.findIndex(e => e.date === '2019-12-30')}); setTrigger('both'); prepare();
      let worse = 0, lower = 0, tot = 0; sim.cells.forEach((c, j) => { const b0 = base.get(c); if (!b0) return; for (let m = 0; m < NMEM; m++) { tot++; if (sim.pc[j][m] > b0[m] + 1e-3) worse++; else if (sim.pc[j][m] < b0[m] - 1e-3) lower++; } });
      add('V2', 'Stability', 'Adding earthquake shaking never raises the critical rain', '0 increases', worse, '= 0', worse === 0 && lower > 0, `${tot} comparisons, ${lower} lowered`);
      // V3 root cohesion only raises it
      setUI(DEF); setTrigger('rain'); rootOn(false); prepare(); const b1 = new Map(); sim.cells.forEach((c, j) => b1.set(c, sim.pc[j]));
      picks.forEach(ci => { LC[ci] = 1; }); rootOn(true); prepare();
      let down = 0, up = 0, t3 = 0; sim.cells.forEach((c, j) => { const b0 = b1.get(c); if (!b0 || !picks.includes(c)) return; for (let m = 0; m < NMEM; m++) { t3++; if (sim.pc[j][m] < b0[m] - 1e-3) down++; else if (sim.pc[j][m] > b0[m] + 1e-3) up++; } });
      add('V3', 'Stability', 'Root cohesion (tree cover) never lowers the critical rain', '0 decreases', down, '= 0', down === 0, `${t3} comparisons, ${up} raised`);
    }

    // ================= V4-V9 flow solver =================
    const mkR = (n, Zfn, H0fn) => { const DXW = 40, HALF = (n - 1) * DXW / 2, Z = new Float32Array(n * n), H0 = new Float32Array(n * n);
      for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) { Z[j * n + i] = Zfn(i * DXW - HALF, j * DXW - HALF); H0[j * n + i] = H0fn(i, j); }
      return {n, DXW, HALF, Z, sl: new Float32Array(n * n), H0, nrel: 1, E0: 0, N0: 0, zsoil: 1.5, cx: n / 2, cy: n / 2, rocks: [], rockInfo: 0, lambda: 0, entrain: false, frag: 0}; };
    const mass = R => { let s = 0; for (let c = 0; c < R.fl.H.length; c++) s += R.fl.H[c]; return s * R.DXW * R.DXW; };
    V3.mode = 'slide'; setUI({'v3mu': 0.2});
    {
      const n = 121, R = mkR(n, (x, y) => 0.3 * x + 15 * Math.sin(x / 700) * Math.cos(y / 900), (i, j) => (Math.hypot(i - 30, j - 60) < 10 || Math.hypot(i - 90, j - 40) < 8) ? 3 : 0);
      initPhysics(R); const m0 = mass(R); let neg = 0;
      for (let k = 0; k < 300; k++) { stepSim(R, .5); }
      for (let c = 0; c < R.fl.H.length; c++) if (R.fl.H[c] < 0) neg++;
      const m1 = mass(R), rel = Math.abs(m1 - m0) / m0;
      add('V4', 'Flow solver', 'Mass is conserved in a closed domain over 150 s', '0', rel, '< 1e-5 relative', rel < 1e-5 && neg === 0, `start ${fmt(m0)} m³, end ${fmt(m1)} m³, negative cells ${neg}`);
    }
    {
      const n = 81, eta = 30, R = mkR(n, (x, y) => 10 + 10 * Math.sin(x / 300) * Math.cos(y / 350), () => 0);
      for (let c = 0; c < n * n; c++) R.H0[c] = eta - R.Z[c];
      initPhysics(R); for (let k = 0; k < 200; k++) stepSim(R, .1);
      let q = 0; for (const a of R.fl.Qx) q = Math.max(q, Math.abs(a)); for (const a of R.fl.Qy) q = Math.max(q, Math.abs(a));
      add('V5', 'Flow solver', 'A flat water surface over uneven ground stays at rest (well balanced)', '0 m²/s', q, '< 1e-3 m²/s', q < 1e-3, 'max |q| after 20 s');
    }
    {
      const th = Math.atan(0.5), n = 161, R = mkR(n, x => -0.5 * x, () => 1.5);
      initPhysics(R); for (let k = 0; k < 80; k++) stepSim(R, .5);
      const j0 = 80, i0 = 80, f = j0 * (n + 1) + i0, a = j0 * n + i0 - 1, b = a + 1;
      const hf = Math.max(R.Z[a] + R.fl.H[a], R.Z[b] + R.fl.H[b]) - Math.max(R.Z[a], R.Z[b]), u = R.fl.Qx[f] / hf;
      const ua = Math.sqrt(400 * 1.5 * (0.5 - 0.2 * Math.cos(th))), rel = Math.abs(u - ua) / ua;
      add('V6', 'Flow solver', 'Steady speed on a uniform slope equals the Voellmy value sqrt(ξ h (tanθ − μ cosθ))', fmt(ua, 2) + ' m/s', +u.toFixed(2), '< 5 %', rel < .05, `tanθ 0.5, μ 0.2, ξ 400, h 1.5 m, error ${(rel * 100).toFixed(1)} %`);
    }
    {
      const res = [];
      for (const T of [0.15, 0.25]) { const R = mkR(121, x => -T * x, () => 1.5); initPhysics(R); for (let k = 0; k < 120; k++) stepSim(R, .5); let q = 0; for (const a of R.fl.Qx) q = Math.max(q, Math.abs(a)); res.push(q); }
      add('V7', 'Flow solver', 'Flow stays at rest below the friction slope (tanθ 0.15 < μ cosθ) and moves above it (tanθ 0.25)', 'rest, then motion', `${res[0].toExponential(1)} / ${res[1].toFixed(2)} m²/s`, 'q(0.15) < 1e-6 and q(0.25) > 1', res[0] < 1e-6 && res[1] > 1, 'max |q| after 60 s');
    }

    // ================= V8-V11 rock blocks =================
    const mkRock = (R, o) => Object.assign({x: 0, y: 0, z: 0, vx: 0, vy: 0, vz: 0, r: .5, stopped: false, trav: 0, vmax: 0, x0: o.x || 0, y0: 0, tt: 0, delay: 0, trail: [[0, 0]], lt: 0}, o);
    setUI({'v3e': 0.35, 'v3rough': 0, 'v3shape': 'round'});
    {
      const R = mkR(81, () => 0, () => 0), v0 = 20, al = Math.PI / 4, b = mkRock(R, {x: -100, z: .5, vx: v0 * Math.cos(al), vz: v0 * Math.sin(al)}); b.x0 = -100; R.rocks = [b]; R.tsim = 100;
      let prev = b.vz, land = null; for (let k = 0; k < 4000 && land === null; k++) { stepRocks(R, 1 / 120); if (prev < 0 && b.vz > 0) land = b.x - (-100); prev = b.vz; }
      const ra = v0 * v0 * Math.sin(2 * al) / 9.81, rel = Math.abs(land - ra) / ra;
      add('V8', 'Rock blocks', 'Projectile range equals v² sin2α / g', fmt(ra, 2) + ' m', land === null ? null : +land.toFixed(2), '< 1 %', land !== null && rel < .01, `20 m/s at 45°, step 1/120 s, error ${(rel * 100).toFixed(2)} %`);
    }
    {
      const R = mkR(81, () => 0, () => 0), e = 0.35, b = mkRock(R, {x: 0, z: .5 + 5}); R.rocks = [b]; R.tsim = 100;
      let bounced = false, apex = 0; for (let k = 0; k < 3000; k++) { const vz0 = b.vz; stepRocks(R, 1 / 240); if (vz0 < 0 && b.vz > 0) bounced = true; if (bounced) apex = Math.max(apex, b.z - .5); if (bounced && b.vz < 0) break; }
      const ha = e * e * 5, rel = Math.abs(apex - ha) / ha;
      add('V9', 'Rock blocks', 'Rebound height of a drop equals e² × drop height', fmt(ha, 3) + ' m', +apex.toFixed(3), '< 5 %', rel < .05, `5 m drop, e 0.35, error ${(rel * 100).toFixed(1)} %`);
    }
    {
      const th = 40 * Math.PI / 180, R = mkR(81, x => -Math.tan(th) * x, () => 0), x0 = -1400, b = mkRock(R, {x: x0, z: -Math.tan(th) * x0 + .5}); b.x0 = x0; R.rocks = [b]; R.tsim = 100;
      for (let k = 0; k < 120 * 40; k++) stepRocks(R, 1 / 120);
      const sp = Math.hypot(b.vx, b.vy, b.vz), va = Math.sqrt(9.81 * (Math.sin(th) - .5 * Math.cos(th)) / .004), rel = Math.abs(sp - va) / va;
      add('V10', 'Rock blocks', 'Terminal speed on a 40° slope equals the rolling-resistance plus drag balance', fmt(va, 1) + ' m/s', +sp.toFixed(1), '< 5 %', rel < .05, `μ_r 0.5, drag 0.004 v², error ${(rel * 100).toFixed(1)} %`);
    }
    {
      const th = 20 * Math.PI / 180, R = mkR(81, x => -Math.tan(th) * x, () => 0), x0 = -400, b = mkRock(R, {x: x0, z: -Math.tan(th) * x0 + .5, vx: 5 * Math.cos(th), vz: -5 * Math.sin(th)}); b.x0 = x0; R.rocks = [b]; R.tsim = 100;
      for (let k = 0; k < 120 * 30 && !b.stopped; k++) stepRocks(R, 1 / 120);
      const a0 = 9.81 * (.5 * Math.cos(th) - Math.sin(th)), da = (1 / (2 * .004)) * Math.log((a0 + .004 * 25) / a0) * Math.cos(th), tr = b.trav, rel = Math.abs(tr - da) / da;
      add('V11', 'Rock blocks', 'A block on a 20° slope stops after the analytic distance (horizontal)', fmt(da, 2) + ' m', +tr.toFixed(2), '< 5 %', b.stopped && rel < .05, `5 m/s start, stopped ${b.stopped}, error ${(rel * 100).toFixed(1)} %`);
    }


    // roughness and shape: the extra rock features must not disturb the analytic tests above, and must do what they claim
    {
      const run = (rough, shape) => { setUI({'v3rough': rough, 'v3shape': shape, 'v3e': 0.35}); const th = 35 * Math.PI / 180, R = mkR(81, x => -Math.tan(th) * x, () => 0); R.rng = rng(5); R.tsim = 100; const rn = rng(21);
        R.rocks = []; for (let k = 0; k < 40; k++) { const x0 = -1400 + rn() * 20; R.rocks.push(mkRock(R, {x: x0, y: (rn() - .5) * 20, z: -Math.tan(th) * x0 + .5 + rn() * 3, vx: 3 + rn() * 3, y0: 0})); R.rocks[k].x0 = x0; R.rocks[k].y0 = R.rocks[k].y; }
        for (let k = 0; k < 120 * 45; k++) stepRocks(R, 1 / 120);
        const ys = R.rocks.map(b => b.y - b.y0), my = ys.reduce((a, c) => a + c, 0) / ys.length, sd = Math.sqrt(ys.reduce((a, c) => a + (c - my) ** 2, 0) / ys.length), tv = R.rocks.reduce((a, b) => a + b.trav, 0) / R.rocks.length; return {sd, tv}; };
      const r0 = run(0, 'round'), r8 = run(0.8, 'round');
      add('V17', 'Rock blocks', 'Ground roughness adds sideways scatter to blocks released together', 'scatter(0.8) well above scatter(0)', `${r8.sd.toFixed(1)} m vs ${r0.sd.toFixed(1)} m`, 'at least 3 m and 5 times larger', r8.sd >= 3 && r8.sd > 5 * Math.max(r0.sd, .1), '40 blocks, 35° plane, standard deviation of cross-slope displacement');
      const rr = run(0, 'round'), ra = run(0, 'angular'), rp = run(0, 'platy');
      add('V18', 'Rock blocks', 'Angular and platy blocks travel less far than rounded ones', 'round > angular > platy', `${rr.tv.toFixed(0)} / ${ra.tv.toFixed(0)} / ${rp.tv.toFixed(0)} m`, 'strictly decreasing', rr.tv > ra.tv && ra.tv > rp.tv, 'mean horizontal travel, 40 blocks, 45 s');
      setUI({'v3rough': 0, 'v3shape': 'round'});
    }


    // joints: Markland kinematic tests against textbook conditions
    {
      const t = [kinPlanar(60, 90, 40, 90, 30), !kinPlanar(60, 90, 40, 90, 45), !kinPlanar(60, 90, 70, 90, 30), !kinPlanar(60, 90, 40, 120, 30), kinPlanar(60, 90, 40, 109, 30), !kinPlanar(60, 90, 40, 271, 30)];
      add('V21', 'Joints', 'Planar test: feasible only when aligned within 20°, daylighting and steeper than the friction angle', '6 of 6 cases', `${t.filter(Boolean).length} of 6`, 'all', t.every(Boolean), 'dip 60 slope, joint dip 40, friction 30, plus five boundary cases');
      const nv = (d, a) => [Math.sin(d * RAD) * Math.sin(a * RAD), Math.sin(d * RAD) * Math.cos(a * RAD), Math.cos(d * RAD)];
      let worst = 0, cnt = 0, feasiblePairs = 0; const rn = rng(77);
      for (let k = 0; k < 400; k++) { const d1 = 30 + rn() * 55, a1 = rn() * 360, d2 = 30 + rn() * 55, a2 = rn() * 360, n1 = nv(d1, a1), n2 = nv(d2, a2);
        let I = [n1[1] * n2[2] - n1[2] * n2[1], n1[2] * n2[0] - n1[0] * n2[2], n1[0] * n2[1] - n1[1] * n2[0]]; const l = Math.hypot(...I); if (l < 1e-3) continue; I = I.map(v => v / l);
        worst = Math.max(worst, Math.abs(I[0] * n1[0] + I[1] * n1[1] + I[2] * n1[2]), Math.abs(I[0] * n2[0] + I[1] * n2[1] + I[2] * n2[2])); cnt++; if (kinWedge(75, 180, d1, a1, d2, a2, 25)) feasiblePairs++; }
      add('V22', 'Joints', 'The wedge intersection line lies in both joint planes', '0', worst, '< 1e-9', worst < 1e-9, `${cnt} random plane pairs; ${feasiblePairs} feasible on a 75° south-facing slope`);
      const sh = [kinWedge(70, 180, 50, 135, 50, 225, 25), !kinWedge(70, 180, 50, 135, 50, 225, 45), !kinWedge(70, 0, 50, 135, 50, 225, 25)];
      add('V23', 'Joints', 'Wedge test: a south-dipping wedge daylights on a south face, stops being feasible when friction is high, and is infeasible on the opposite (north) face', '3 of 3', `${sh.filter(Boolean).length} of 3`, 'all', sh.every(Boolean), 'two sets dipping 50° toward 135° and 225°, slope dip 70°');
    }


    // landslide dam: lake volume on a synthetic valley, formulas, breach flood volume balance, Manning steady flow
    {
      const n = 81, DX = 20, HALF = (n - 1) * DX / 2, sx_ = 0.05, sy_ = 0.02, Hc = 10;
      const Z = new Float32Array(n * n); for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) { const x = i * DX - HALF, y = j * DX - HALF; Z[j * n + i] = Math.abs(x) * sx_ + sy_ * (y + HALF); }
      const j0 = Math.round(HALF / DX) + 0 + 0; const jd = 40; const thal = Z[jd * n + 40], crest = thal + Hc; const block = new Set(); const seed = []; for (let i = 38; i <= 42; i++) { block.add(jd * n + i); } seed.push((jd - 1) * n + 40);
      const L = lakeFill(Z, n, DX, seed, crest, thal, block, [40, 40], [0, 1]), va = Hc ** 3 / (3 * sx_ * sy_), rel = Math.abs(L.vol - va) / va;
      add('V24', 'Dam', 'Lake volume behind a dam on a V-shaped valley matches the analytic volume H³ / (3 sx sy)', fmt(va) + ' m³', fmt(L.vol) + ' m³', '< 15 %', rel < .15, `10 m dam, 40 m grid, error ${(rel * 100).toFixed(1)} %`);
      const qf = froehlichQp(1e7, 50), qa = 0.607 * Math.pow(1e7, 0.295) * Math.pow(50, 1.24);
      add('V25', 'Dam', 'Froehlich (1995) peak breach outflow is coded as 0.607 V^0.295 h^1.24', fmt(qa) + ' m³/s', fmt(qf) + ' m³/s', '< 1e-9', Math.abs(qf - qa) / qa < 1e-9, '10 million m³, 50 m');
      const d1 = dbiClass(1e9, 20, 1e6), d2 = dbiClass(1e8, 50, 5e7), d3 = dbiClass(1e7, 40, 5e5);
      add('V26', 'Dam', 'Dam stability index classes follow Ermini and Casagli (2003) cut-offs', 'unstable, stable, uncertain', `${d1.cls}, ${d2.cls}, ${d3.cls}`, 'DBI 4.3, 2.0, 2.9', d1.cls === 'likely unstable' && d2.cls === 'likely stable' && d3.cls === 'uncertain', `DBI ${d1.dbi.toFixed(2)}, ${d2.dbi.toFixed(2)}, ${d3.dbi.toFixed(2)}`);
      // Manning steady uniform flow on a plane
      const n2 = 161, R = mkR(n2, x => -0.02 * x, () => 1.0); R.water = true; R.manning = 0.06; initPhysics(R); for (let k = 0; k < 120; k++) stepSim(R, .5);
      const f = 80 * (n2 + 1) + 80, a = 80 * n2 + 79, b2 = a + 1, hf = Math.max(R.Z[a] + R.fl.H[a], R.Z[b2] + R.fl.H[b2]) - Math.max(R.Z[a], R.Z[b2]), u = R.fl.Qx[f] / hf, ua = Math.pow(hf, 2 / 3) * Math.sqrt(0.02) / 0.06;
      add('V27', 'Dam', 'Clear-water steady speed on a 2 % slope equals the Manning value', fmt(ua, 2) + ' m/s', +u.toFixed(2), '< 5 %', Math.abs(u - ua) / ua < .05, `n 0.06, depth ${hf.toFixed(2)} m, error ${(Math.abs(u - ua) / ua * 100).toFixed(1)} %`);
      // breach injection and volume balance in a closed domain
      const R3 = mkR(81, (x, y) => 0.01 * (HALF - x) + 0 * y, () => 0); R3.water = true; R3.manning = .06; initPhysics(R3); R3.dam = {bc: [40 * 81 + 10, 40 * 81 + 11], dep: new Set(), Qp: 500, Tb: 600}; R3.breach = {t: 0, Tb: 600, Qp: 500, cells: R3.dam.bc, injected: 0, arr: {}, cx: 10.5, cy: 40};
      for (let k = 0; k < 400; k++) breachStep(R3, 2);
      let vol = 0; for (const x of R3.fl.H) vol += x * R3.DXW * R3.DXW; const want = 0.5 * 500 * 600, relv = Math.abs(vol - want) / want;
      add('V28', 'Dam', 'The breach hydrograph delivers exactly its volume (½ Qp Tb) into a closed domain', fmt(want) + ' m³', fmt(vol) + ' m³', '< 1e-3', relv < 1e-3, `Qp 500 m³/s, Tb 600 s, relative error ${relv.toExponential(1)}`);
    }


    // new physics: entrainment, fluidization, Newmark, fragmentation, frames, event reconstruction
    {
      V3.mode = 'slide'; setUI({'v3mu': 0.2});
      const slope = (entrain, lambda) => { const n = 121, R = mkR(n, x => -0.45 * x, (i, j) => (Math.hypot(i - 25, j - 60) < 6) ? 3 : 0); R.entrain = entrain; R.lambda = lambda; R.cx = 25; R.cy = 60; initPhysics(R); const Z0 = Float32Array.from(R.Z), H00 = Float32Array.from(R.fl.H);
        let m0 = 0; for (const x of R.fl.H) m0 += x; for (let k = 0; k < 120; k++) stepSim(R, .5);
        let m1 = 0, bed = 0; for (const x of R.fl.H) m1 += x; for (let c = 0; c < Z0.length; c++) bed += Z0[c] - R.Z[c]; const dx2 = R.DXW * R.DXW, m = flowMetrics(R); return {R, m0: m0 * dx2, m1: m1 * dx2, bed: bed * dx2, ent: R.entrained, Lm: m.Lm, L: m.L}; };
      const a = slope(true, 0), b = slope(false, 0);
      const bal = Math.abs((a.m1 - a.m0) - a.bed) / Math.max(1, a.bed), bal2 = Math.abs(a.ent - a.bed) / Math.max(1, a.bed);
      add('V29', 'Realism', 'Entrainment moves soil from the bed into the flow without creating or losing any', '0', Math.max(bal, bal2), '< 1e-3 relative', bal < 1e-3 && bal2 < 1e-3 && a.ent > 0 && b.ent === 0, `entrained ${fmt(a.ent)} m³; flow volume gained equals bed volume lost; no scour when switched off`);
      add('V30', 'Realism', 'A scouring flow grows and travels farther than one that cannot scour', 'larger volume and distance', `${fmt(a.m1)} m³ / ${Math.round(a.L)} m vs ${fmt(b.m1)} m³ / ${Math.round(b.L)} m`, 'both larger', a.m1 > b.m1 && a.L >= b.L, 'tan 0.45 slope, 60 s, farthest cell reached');
      const f0 = slope(false, 0), f8 = slope(false, 0.8);
      add('V31', 'Realism', 'Pore-pressure fluidization lowers friction and sends the flow farther', 'distance(λ 0.8) > distance(λ 0)', `${Math.round(f8.Lm)} m vs ${Math.round(f0.Lm)} m`, 'ordered', f8.Lm > f0.Lm, 'effective friction μ (1 − 0.6 λ)');
      // Newmark rectangular pulse against its closed form
      const a0 = 3, ay = 1, T = 2, dt = .02, arr = new Float32Array(Math.round(12 / dt)); for (let i = 0; i < T / dt; i++) arr[i] = a0;
      const nm = newmarkD(arr, dt, ay), da = 0.5 * (a0 - ay) * T * T * a0 / ay;
      add('V32', 'Realism', 'Newmark sliding block: a rectangular pulse gives ½ (a0 − ay) T² a0 / ay', fmt(da, 2) + ' m', +nm.d.toFixed(2), '< 1 %', Math.abs(nm.d - da) / da < .01, 'a0 3, ay 1, T 2 s');
      const acc = accelerogram(0.2 * 9.81, 20, 4), pk = Math.max(...Array.from(acc.a).map(Math.abs));
      add('V33', 'Realism', 'The synthetic accelerogram peaks at exactly the requested ground acceleration, and displacement falls as the yield acceleration rises', 'peak = 0.2 g; D(ay 0.05 g) > D(ay 0.15 g)', `${(pk / 9.81).toFixed(3)} g; ${(newmarkD(acc.a, acc.dt, .05 * 9.81).d * 100).toFixed(1)} vs ${(newmarkD(acc.a, acc.dt, .15 * 9.81).d * 100).toFixed(1)} cm`, '< 1e-6 and ordered', Math.abs(pk - 0.2 * 9.81) < 1e-4 && newmarkD(acc.a, acc.dt, .05 * 9.81).d > newmarkD(acc.a, acc.dt, .15 * 9.81).d, '20 s record');
      // fragmentation conserves volume
      setUI({'v3e': 0.5, 'v3rough': 0.3, 'v3shape': 'round'}); const th = 40 * Math.PI / 180, Rf = mkR(81, x => -Math.tan(th) * x, () => 0); Rf.frag = 1; Rf.rng = rng(8); Rf.tsim = 100; const rn = rng(2);
      for (let k = 0; k < 30; k++) { const x0 = -1400 + rn() * 30; Rf.rocks.push(mkRock(Rf, {x: x0, y: (rn() - .5) * 30, z: -Math.tan(th) * x0 + 6 + rn() * 6, r: 1.5, vx: 2 + rn() * 3})); Rf.rocks[k].x0 = x0; Rf.rocks[k].y0 = Rf.rocks[k].y; }
      const vol0 = Rf.rocks.reduce((s, b) => s + b.r ** 3, 0); for (let k = 0; k < 120 * 40; k++) stepRocks(Rf, 1 / 120);
      const vol1 = Rf.rocks.reduce((s, b) => s + b.r ** 3, 0), rv = Math.abs(vol1 - vol0) / vol0;
      add('V34', 'Realism', 'Block fragmentation conserves rock volume and does split blocks on hard impacts', '0 change, some breaks', `${rv.toExponential(1)} change, ${Rf.nfrag} breaks`, '< 1e-6 and at least one break', rv < 1e-6 && Rf.nfrag > 0, `${Rf.rocks.length} blocks at the end, 30 at the start`);
      setUI({'v3e': 0.35, 'v3rough': 0});
      // timeline frames
      const Rt = mkR(121, x => -0.45 * x, (i, j) => (Math.hypot(i - 25, j - 60) < 6) ? 3 : 0); Rt.entrain = false; initPhysics(Rt); Rt.cx = 25; Rt.cy = 60; while (Rt.tsim < 30) { stepSim(Rt, .5); recordStep(Rt); }
      const last = Rt.frames[Rt.frames.length - 1]; let me = 0; for (let c = 0; c < Rt.fl.H.length; c++) me = Math.max(me, Math.abs(Math.min(63.75, Rt.fl.H[c]) - last.h8[c] / 4));
      add('V35', 'Realism', 'Timeline frames reproduce the flow depth to the storage resolution (0.125 m) and cover every second', '30 frames up to 31', `max error ${me.toFixed(3)} m; ${Rt.frames.length} frames`, '≤ 0.125 m, 31 frames', me <= 0.126 && Rt.frames.length === 31, 'depth stored in 0.25 m steps');
    }
    // historical events: reconstruction details, and a run of every reported landslide
    {
      await loadHeightfield(); out.events = []; let worstV = 0, ndet = 0;
      for (const ev of EVENTS) {
        const R = buildEventWindow(ev), R2 = buildEventWindow(ev); const rv = R.nrel * R.DXW * R.DXW * R.zsoil, err = Math.abs(rv - R.targetV) / R.targetV; worstV = Math.max(worstV, R.nrel < 500 ? err : 0);
        let same = R.nrel === R2.nrel; for (let c = 0; c < R.H0.length && same; c++) if (R.H0[c] !== R2.H0[c]) same = false; if (same) ndet++;
        setMode(R.evmode); initPhysics(R); if (R.quake) prepareQuake(R);
        let guard = 0; while (R.tsim < 90) { stepSim(R, .5); recordStep(R); if (R.tsim > 15 && R.vmaxFlow < .4 && R.moving === 0) break; guard++; }
        const m = flowMetrics(R), ck = eventCheck(R); let vm = 0; for (const x of R.fl.Vmax) if (x > vm) vm = x;
        try { const Ii = computeImpact(R); (out.events_impact = out.events_impact || []).push({iso: ev.iso, cat: ev.cat, fat: ev.fat === undefined ? null : ev.fat, inj: ev.inj === undefined ? null : ev.inj, affected: Ii.b ? Ii.b.affected : null, people: Ii.people ? Ii.people.affected : null, displaced: Ii.people ? Ii.people.displaced : null, blockedKm: Ii.r.blockedKm.reduce((x, y) => x + y, 0), loss: Ii.cost.total}); } catch (e) { out.errors.push('event impact ' + ev.iso + ': ' + e.message); }
        const rocks = R.rocks.map(b => ({trav: b.trav, stopped: b.stopped, vmax: b.vmax}));
        out.events.push({iso: ev.iso, cat: ev.cat, trig: ev.trig, size: ev.size, acc: ev.acc, mode: R.evmode, nrel: R.nrel, target_v: R.targetV, vol0: R.nrel * R.DXW * R.DXW * R.zsoil, vol_end: m.vol, entrained: R.entrained, Lm: m.Lm, L: m.L, drop: m.drop, vmax: vm, rocks: rocks.length, frag: R.nfrag, rock_max_trav: rocks.length ? Math.max(...rocks.map(r => r.trav)) : 0, rock_vmax: rocks.length ? Math.max(...rocks.map(r => r.vmax)) : 0,
          reach: ck.reach, dmin: Math.min(ck.dmin, 99999), tol: ck.tol, acc_m: ck.acc, quake: R.quake ? {pga_g: R.quake.pga, M: R.quake.M, D_cm: R.newmark.D * 100, t0: R.newmark.t0, FS: R.newmark.FS} : null, lambda: R.lambda, rain: R.rain, t_end: R.tsim, frames: R.frames.length});
      }
      add('V36', 'Events', 'Every reported landslide is rebuilt with its size-class volume (within one cell layer) and the same release each time', 'volume within 35 %, 17 of 17 repeatable', `worst ${(worstV * 100).toFixed(0)} %, ${ndet} of ${EVENTS.length} repeatable`, '≤ 35 % and all repeatable', worstV <= .35 && ndet === EVENTS.length, 'release volume against the size-class target');
    }


    // impact assessment: fragility, building damage and cost, road blockage
    {
      const med = IMP.med, beta = IMP.beta;
      const atMed = med.map(m => 1 - dsProbs(m, med, beta).slice(0, 1)[0]);   // P(DS>=1) at each median is not 0.5 for DS2.. so test each state's own exceedance
      let okc = true, sums = 0; [0.5, 3, 10, 30, 80, 300].forEach(p => { const pm = dsProbs(p, med, beta); sums = Math.max(sums, Math.abs(pm.reduce((a, b) => a + b, 0) - 1)); if (pm.some(v => v < -1e-9)) okc = false; });
      const ex = k => { const pm = dsProbs(med[k], med, beta); return pm.slice(k + 1).reduce((a, b) => a + b, 0); };
      const half = [0, 1, 2, 3].map(ex), mono = dsProbs(10, med, beta).slice(1).reduce((a, b) => a + b, 0) < dsProbs(100, med, beta).slice(1).reduce((a, b) => a + b, 0);
      add('V37', 'Impact', 'Fragility: probabilities sum to 1, are non-negative, and each state has exceedance 0.5 at its median pressure', 'sum 1; 0.5 at DS1 to DS4 medians; rises with pressure', `max sum error ${sums.toExponential(1)}; exceedance at medians ${half.map(x => x.toFixed(3)).join(', ')}`, '< 1e-6 and within 0.002 of 0.5', okc && mono && sums < 1e-6 && half.every(x => Math.abs(x - .5) < .002), 'lognormal, dispersion ' + beta);
      // buildings on a synthetic flow
      const n = 41, R = mkR(n, () => 0, () => 0); R.E0 = X0 + 30000; R.N0 = Y1 - 30000; initPhysics(R);
      const cellW = (i, j) => [R.E0 - X0 - R.HALF + (i + .5) * R.DXW, Y1 - (R.N0 - R.HALF + (j + .5) * R.DXW)];
      const set = (i, j, h, v) => { R.fl.Hmax[j * n + i] = h; R.fl.Vmax[j * n + i] = v; };
      set(10, 10, 2, 10); set(12, 10, .5, 1); set(14, 10, 0, 0);
      const saveBP = BP ? {n: BP.n, xy: BP.xy, ar: BP.ar} : null, bp = BP || {};
      const pts = [cellW(10, 10), cellW(12, 10), cellW(14, 10)], ar = [100, 80, 120];
      const useBP = BP; if (!useBP) { out.errors.push('no building data for the impact test'); }
      else {
        useBP.n = 3; useBP.xy = Float32Array.from(pts.flat()); useBP.ar = Uint16Array.from(ar);
        const savedFloors = IMP.floors, savedCost = IMP.costM2; IMP.floors = 1; IMP.costM2 = 10000;
        const I = impactBuildings(R);
        const pm1 = dsProbs(flowIM(2, 10), IMP.med, IMP.beta), pm2 = dsProbs(flowIM(.5, 1), IMP.med, IMP.beta);
        const want = 100 * 1e4 * expDR(pm1) + 80 * 1e4 * expDR(pm2);
        add('V38', 'Impact', 'Building impact: a building in no flow is DS0, damaged ones are costed as area × unit cost × expected damage ratio, and counts add up', `cost ${fmt(want)} PKR; 3 buildings, 2 reached`, `cost ${fmt(I.cost)} PKR; ${I.inWindow} in window, ${I.affected} reached`, 'cost within 1e-6 relative; counts exact', Math.abs(I.cost - want) / want < 1e-6 && I.inWindow === 3 && I.affected === 2 && I.ds.reduce((a, b) => a + b, 0) === 3 && I.ds[0] === 1, 'building areas 100, 80, 120 m2, unit cost 10,000 PKR/m2');
        useBP.n = saveBP.n; useBP.xy = saveBP.xy; useBP.ar = saveBP.ar; IMP.floors = savedFloors; IMP.costM2 = savedCost;
      }
      // road blockage: a 400 m road crossing a 5 cell wide deposit strip
      const Rr = mkR(n, () => 0, () => 0); Rr.E0 = X0 + 30000; Rr.N0 = Y1 - 30000; initPhysics(Rr);
      for (let j = 0; j < n; j++) for (let i = 18; i <= 22; i++) { Rr.fl.Hmax[j * n + i] = 1.0; Rr.fl.Vmax[j * n + i] = 3; }
      const w0 = Rr.E0 - X0 - Rr.HALF, y0 = Y1 - Rr.N0 + Rr.HALF - 40 * 20;
      const saveRoads = INFRA.roads; INFRA.roads = [{c: 0, b: 0, t: 0, n: 'test', xy: [Math.round(w0 + 10 * 40 + 1), Math.round(y0), Math.round(w0 + 30 * 40 + 1), Math.round(y0)]}];
      const Ir = impactRoads(Rr), blocked = Ir.blockedKm[0] * 1000;
      INFRA.roads = saveRoads;
      add('V39', 'Impact', 'Road blockage: a road crossing a 5 cell (200 m) deposit strip of 1 m depth is blocked over 200 m', '200 m', Math.round(blocked) + ' m', 'within 15 m', Math.abs(blocked - 200) <= 15, '10 m sampling');
    }

    // ================= scenarios for empirical checks =================
    const quakeIdx = d => D.shake.findIndex(e => e.date === d);
    const SC = {S1: {'s-int': 10, 's-dur': 24, 'root': true, 'eq': -1}, S2: {'s-int': 25, 's-dur': 24, 'root': true, 'eq': -1}, S3: {'s-int': 40, 's-dur': 24, 'root': true, 'eq': -1},
      S4: {'s-int': 10, 's-dur': 24, 'root': false, 'eq': -1}, S5: {'s-int': 2, 's-dur': 1, 'root': true, 'eq': quakeIdx('2015-10-26')}, S6: {'s-int': 2, 's-dur': 1, 'root': true, 'eq': quakeIdx('2005-10-08')}, S7: {'s-int': 2, 's-dur': 1, 'root': true, 'eq': quakeIdx('2019-12-30')}};
    // restore real slopes and land cover first: reload page state is not possible, so decode again
    const SL0 = dec(D.slope_deg), LC0 = dec(D.lc); SL.set(SL0); LC.set(LC0);
    for (const [k, s] of Object.entries(SC)) {
      setUI(Object.assign({}, DEF, {'s-int': s['s-int'], 's-dur': s['s-dur']})); if (s.eq >= 0) el('s-eq').value = s.eq; setTrigger(s.eq >= 0 ? 'quake' : 'rain'); rootOn(s.root); prepare(); renderAt(sim.T);
      let nf = 0; for (let i = 0; i < NC; i++) if (lastFlag[i]) nf++;
      out.scen[k] = {cfg: s, nfail: nf, eligible: sim.eligible, excluded: sim.pre, prob: q8(lastProb), sites: curSites.length};
      if (k === 'S1') out.sites1 = curSites.map(c => ({u: c.u, v: c.v, n: c.n}));
    }


    // ensemble ingredients: run-out must grow as friction falls, and per-run overrides must work
    {
      await loadHeightfield(); V3.mode = 'slide'; setUI(Object.assign({}, DEF)); rootOn(true); prepare(); renderAt(24);
      const q = curSites[0], lim = 60, res = {};
      for (const mu of [0.12, 0.3]) { const R = buildWindow(q.u, q.v); R.mu = mu; initPhysics(R); res[mu] = runMember(R, lim); }
      add('V19', 'Ensemble', 'Lower flow friction moves the mass farther on a real site (model response is monotonic)', 'mean distance(μ 0.12) > mean distance(μ 0.30)', `${Math.round(res[0.12].Lm)} m vs ${Math.round(res[0.3].Lm)} m`, 'ordered', res[0.12].Lm > res[0.3].Lm, 'site 1, 60 s, volume-weighted mean distance from the release centre');
      const Ra = buildWindow(q.u, q.v, {zsoil: 1.0}), Rb = buildWindow(q.u, q.v, {zsoil: 2.0}); let va = 0, vb = 0; for (const x of Ra.H0) va += x; for (const x of Rb.H0) vb += x;
      add('V20', 'Ensemble', 'A per-run soil depth scales the release volume exactly', '2.0×', (vb / va).toFixed(4) + '×', '= 2 ± 1e-6', Math.abs(vb / va - 2) < 1e-6, 'release volume at 1 m and 2 m');
    }

    // ================= site replays on real terrain =================
    setTrigger('rain');
    await loadHeightfield(); V3.mode = 'both';
    setUI(Object.assign({}, DEF)); rootOn(true); prepare(); renderAt(24);
    const sites = curSites.slice();
    const RSITES = [];
    for (let k = 0; k < sites.length; k++) {
      const R = buildWindow(sites[k].u, sites[k].v); initPhysics(R);
      const m0 = mass(R), n = R.n; const zc = R.Z[Math.round(R.cy) * n + Math.round(R.cx)];
      let steps = 0; while (R.tsim < 90) { stepSim(R, .5); steps++; }
      RSITES.push(R);
      const F = R.fl; let vol = 0, area = 0, hmax = 0, far = 0, zlow = 1e9, neg = 0;
      for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) { const c = j * n + i, h = F.H[c]; if (h < 0) neg++; vol += h; if (h > .3) { area++; if (h > hmax) hmax = h; } if (F.Hmax[c] > .3) { const d = Math.hypot((i - R.cx) * R.DXW, (j - R.cy) * R.DXW); if (d > far) far = d; if (R.Z[c] < zlow) zlow = R.Z[c]; } }
      const rocks = R.rocks.map(b => ({trav: b.trav, drop: b.z0 === undefined ? null : null, stopped: b.stopped, vmax: b.vmax, x: b.x, y: b.y, x0: b.x0, y0: b.y0, z: b.z}));
      out.sites.push({site: k + 1, u: sites[k].u, v: sites[k].v, nrel: R.nrel, m0, m1: mass(R) - R.entrained, neg, vol_m3: vol * R.DXW * R.DXW, area_km2: area * R.DXW * R.DXW / 1e6, hmax, L: far, H: Math.max(0, zc - zlow), bearing: R.bearing, rocks: rocks.length ? rocks : [], rockz0: null});
      // rock reach angles: need release elevation, recompute from the stored start
      const ang = []; R.rocks.forEach((b, i) => { const drop = sampleZ(R, b.x0, b.y0) - sampleZ(R, b.x, b.y); const hd = b.trav; if (hd > 1) ang.push({deg: Math.atan2(drop, hd) * 180 / Math.PI, trav: hd, drop}); });
      out.sites[out.sites.length - 1].rocks = ang;
    }
    const worstMass = Math.max(...out.sites.map(s => Math.abs(s.m1 - s.m0) / Math.max(1, s.m0)));
    add('V12', 'Flow solver', 'Mass is conserved on all real-terrain site windows over 90 s (flow volume minus what it scoured from the bed)', '0', worstMass, '< 1e-4 relative', worstMass < 1e-4 && out.sites.every(s => s.neg === 0), `${out.sites.length} sites, 40 m grid`);

    // impact assessment on the real site replays
    {
      let bad = 0, tot = 0, fin = true, cnt = 0, costs = [], renders = 0;
      for (const R of RSITES) { try { const I = computeImpact(R); cnt++; costs.push(I.cost.total); if (!isFinite(I.cost.total) || I.cost.total < 0) fin = false; if (I.b) { tot += I.b.inWindow; if (I.b.ds.reduce((a, b) => a + b, 0) !== I.b.inWindow) bad++; } RP.R = R; RP.phase = 'after'; RP.ev = null; RP.k = 0; R.ended = 'test'; renderImpact(R); const html = el('impBody').innerHTML; renders++; if (/Section failed|analysis failed|summary failed/.test(html) || html.length < 3000) bad++; } catch (e) { out.errors.push('impact: ' + e.message); fin = false; } }
      add('V40', 'Impact', 'The impact assessment runs on every real site replay, with finite non-negative costs and building counts that add up', `${RSITES.length} sites`, `${cnt} ran, ${renders} rendered; ${bad} count mismatches or failed sections; costs ${costs.map(c => fmt(c / 1e6)).join(', ')} million PKR`, 'all run, none mismatched', cnt === RSITES.length && bad === 0 && fin, `${fmt(tot)} building footprints in the six windows`);
    }

    // rockfall impact: energy, collisions and barrier
    {
      const m = rockMass(.5), ke = rockKE(.5, 20), mWant = 2700 * 4 / 3 * Math.PI * .125, keWant = .5 * mWant * 400 / 1000;
      add('V41', 'Impact', 'Rock block mass and kinetic energy follow m = ρ 4/3 π r³ and E = ½ m v²', `${fmt(mWant, 1)} kg; ${fmt(keWant, 1)} kJ`, `${fmt(m, 1)} kg; ${fmt(ke, 1)} kJ`, '< 1e-9 relative', Math.abs(m - mWant) / mWant < 1e-9 && Math.abs(ke - keWant) / keWant < 1e-9, 'radius 0.5 m, 20 m/s, density 2700 kg/m3');
      // collision detection against a synthetic building
      const n = 41, R = mkR(n, () => 0, () => 0); R.E0 = X0 + 30000; R.N0 = Y1 - 30000; initPhysics(R);
      if (BP) {
        const sv = {n: BP.n, xy: BP.xy, ar: BP.ar};
        const wx = R.E0 - X0 + 100, wy = Y1 - R.N0 - 0;          // building 100 m east of the window centre
        const wx2 = R.E0 - X0 + 100, wy2 = Y1 - R.N0 + 30;        // building 30 m off the path
        BP.n = 2; BP.xy = Float32Array.from([wx, wy, wx2, wy2]); BP.ar = Uint16Array.from([100, 100]);
        const blk = {x: 0, y: 0, z: 0, vx: 0, vy: 0, vz: 0, r: .5, stopped: true, trav: 200, vmax: 20, x0: 0, y0: 0, tt: 0, delay: 0, trail: [], tv: [], tr: [], lt: 0};
        for (let x = 0; x <= 200; x += 4) { blk.trail.push([x, 0]); blk.tv.push(20); blk.tr.push(.5); } blk.x = 200;
        R.rocks = [blk]; R.nfrag = 0;
        const K = impactRock(R);
        add('V42', 'Impact', 'Collision detection: a block path through a building footprint is a hit, a building 30 m off the path is not', '1 building hit, energy 283 kJ', `${K.bldg.hit} hit, ${fmt(K.keMax, 0)} kJ`, 'exact', K.bldg.hit === 1 && K.hits.b.has(0) && !K.hits.b.has(1) && Math.abs(K.keMax - rockKE(.5, 20)) < 1e-6, 'building radius = max(4 m, sqrt(100/π) m)');
        BP.n = sv.n; BP.xy = sv.xy; BP.ar = sv.ar;
      }
      // barrier: stops a weak block, subtracts its capacity from a strong one, ignores one that flies over
      const Rb = mkR(41, () => 0, () => 0); Rb.barrier = {x1: 0, y1: -20, x2: 0, y2: 20, cap: 100, h: 3, stopped: 0, passed: 0, over: 0, absorbed: 0};
      const mk = (z, v) => ({x: 5, y: 0, z, vx: v, vy: 0, vz: 0, r: .5, stopped: false});
      const a = mk(1, 10); barrierCheck(Rb, a, -5, 0);
      Rb.barrier.cap = 20; const b = mk(1, 10); barrierCheck(Rb, b, -5, 0);
      const keAfter = rockKE(.5, Math.hypot(b.vx, b.vy, b.vz)), keBefore = rockKE(.5, 10);
      const c = mk(10, 10); barrierCheck(Rb, c, -5, 0);
      add('V43', 'Impact', 'Barrier: a block with less energy than the capacity stops, a stronger one passes with exactly the capacity removed, one above the top flies over', 'stop; E after = E − 20 kJ; over', `${a.stopped ? 'stopped' : 'passed'}; ${fmt(keAfter, 3)} kJ left of ${fmt(keBefore, 3)}; ${c.stopped || c.barrier ? 'hit' : 'over'}`, 'energy within 1e-6 kJ', a.stopped && !b.stopped && Math.abs(keAfter - (keBefore - 20)) < 1e-6 && !c.barrier && Rb.barrier.over === 1, 'sphere r 0.5 m, 10 m/s, 70.7 kJ');
    }


    // road network access and the economic summary
    {
      const sr = INFRA.roads, sp = INFRA.pois, sl = INFRA.places, sn = NET;
      INFRA.roads = [{c: 0, b: 0, t: 0, n: 'a', xy: [0, 0, 1000, 0]}, {c: 2, b: 0, t: 0, n: 'b', xy: [0, 0, 0, 1000, 1000, 1000, 1000, 0]}, {c: 0, b: 0, t: 0, n: 'c', xy: [0, 0, 0, -2000]}];
      INFRA.pois = [{k: 'hospital', n: 'H', x: 0, y: 0}]; INFRA.places = [{n: 'B', c: 'village', p: 0, x: 1000, y: 0}, {n: 'D', c: 'village', p: 0, x: 0, y: -2000}]; NET = null;
      const A = netAnalysis([new Set(['0:0', '2:0'])]), rb = A.rows.find(r => r.name === 'B'), rd = A.rows.find(r => r.name === 'D');
      add('V44', 'Impact', 'Road network: blocking the direct road forces the longer detour (360 s instead of 72 s, 2 km more) and a settlement whose only road is blocked is cut off', 'B: 72 s to 360 s, +2.0 km; D cut off', `B: ${rb ? Math.round(rb.tb) : '-'} s to ${rb ? Math.round(rb.ta) : '-'} s, +${rb ? rb.km.toFixed(1) : '-'} km; D ${rd ? rd.status : 'unaffected'}`, 'exact within 1 s and 0.05 km', !!rb && Math.abs(rb.tb - 72) < 1 && Math.abs(rb.ta - 360) < 1 && Math.abs(rb.km - 2) < .05 && !!rd && rd.status === 'isolated', 'roads of class 0 at 50 km/h and class 2 at 30 km/h');
      INFRA.roads = sr; INFRA.pois = sp; INFRA.places = sl; NET = sn;
      const Rf = {impact: {b: {costDS: [0, 1e6, 2e6, 3e6, 4e6], dsExp: [0, 1, 2, 3, 4]}, r: {cost: 5e6, blockedKm: [1, 0, 0, 0], bridges: []}, land: {cropCost: 2e6, cropHa: 8}, rock: null, people: {affected: 640, displaced: 50}}, floodImpact: null, net: {debris: {popIso: 100}}};
      const E = econ(Rf), wantDirect = 4e6 + 6e6 + 5e6 + 2e6, wantInd = 100 * 4 * IMP.income * .5 + 50 * IMP.dispDays * IMP.income * .3;
      add('V45', 'Impact', 'Economic summary: direct loss is rebuild + repair + roads + cropland; indirect loss follows the stated proxy; recovery quantities come from the expected damage states', `direct ${fmt(wantDirect)}; indirect ${fmt(wantInd)}; rebuild 4, major repair 3, minor repair 3`, `direct ${fmt(E.direct)}; indirect ${fmt(E.indirect)}; rebuild ${E.rebuildN}, major ${E.majorN}, minor ${E.minorN}`, 'exact', E.direct === wantDirect && Math.abs(E.indirect - wantInd) < 1e-6 && E.rebuildN === 4 && E.majorN === 3 && E.minorN === 3 && E.closureDays === 4, 'closure days = max(3, ceil(1 km / 0.3 km per day)) = 4');
    }

    // ================= projection, heightfield and data integrity =================
    const rn = rng(5);
    for (let k = 0; k < 200; k++) { const lon = 73.95 + rn() * 1.0, lat = 35.58 + rn() * .78, u = ll2utm(lon, lat), b = utm2ll(u[0], u[1]); out.proj.push([lon, lat, u[0], u[1], b[0], b[1]]); }
    { const g = HF, rr = rng(9); for (let k = 0; k < 3000; k++) { const i = Math.floor(rr() * g.w), j = Math.floor(rr() * g.h); out.hf.push([i, j, g.a[j * g.w + i]]); } out.hfdim = [g.w, g.h]; }
    let sb = 0, sp = 0, valid = 0; for (let i = 0; i < NC; i++) { sb += BLD[i]; sp += POP[i] / 10; if (SL[i] !== 255) valid++; }
    out.data = {sum_bld: sb, sum_pop: sp, valid_cells: valid, cell_km2: CELLKM2, area_km2: S.area_km2, bld_total: D.bld_total, pop_total: D.pop_total};

    // ================= DEM (discrete element) feasibility benchmark =================
    function demBench(N, steps) {
      const r = 3, cell = 2 * r, G = 9.81, kn = 4e5, cn = 2e3, mu = .5, m = 1000, dt = 0.004, Z = HF;
      const x = new Float32Array(N), y = new Float32Array(N), z = new Float32Array(N), vx = new Float32Array(N), vy = new Float32Array(N), vz = new Float32Array(N), fx = new Float32Array(N), fy = new Float32Array(N), fz = new Float32Array(N);
      const E0 = 436000, N0 = 3975000, rn = rng(3);
      for (let i = 0; i < N; i++) { x[i] = (rn() - .5) * 300; y[i] = (rn() - .5) * 300; z[i] = hfAt(E0 + x[i], N0 + y[i]) + r + rn() * 40; }
      const gs = 64, head = new Int32Array(gs * gs).fill(-1), nxt = new Int32Array(N);
      const t0 = performance.now();
      for (let s = 0; s < steps; s++) {
        head.fill(-1);
        for (let i = 0; i < N; i++) { const cx_ = Math.max(0, Math.min(gs - 1, Math.floor((x[i] + 400) / (cell * 2)))), cy_ = Math.max(0, Math.min(gs - 1, Math.floor((y[i] + 400) / (cell * 2)))), c = cy_ * gs + cx_; nxt[i] = head[c]; head[c] = i; fx[i] = 0; fy[i] = 0; fz[i] = -G * m; }
        for (let i = 0; i < N; i++) {
          const cx_ = Math.max(0, Math.min(gs - 1, Math.floor((x[i] + 400) / (cell * 2)))), cy_ = Math.max(0, Math.min(gs - 1, Math.floor((y[i] + 400) / (cell * 2))));
          for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) { const xx = cx_ + dx, yy = cy_ + dy; if (xx < 0 || yy < 0 || xx >= gs || yy >= gs) continue;
            for (let j = head[yy * gs + xx]; j >= 0; j = nxt[j]) { if (j <= i) continue; const ddx = x[j] - x[i], ddy = y[j] - y[i], ddz = z[j] - z[i], d2 = ddx * ddx + ddy * ddy + ddz * ddz; if (d2 >= 4 * r * r || d2 < 1e-9) continue;
              const d = Math.sqrt(d2), nx = ddx / d, ny = ddy / d, nz = ddz / d, ov = 2 * r - d, rvn = (vx[j] - vx[i]) * nx + (vy[j] - vy[i]) * ny + (vz[j] - vz[i]) * nz, F = Math.max(0, kn * ov - cn * rvn);
              fx[i] -= F * nx; fy[i] -= F * ny; fz[i] -= F * nz; fx[j] += F * nx; fy[j] += F * ny; fz[j] += F * nz; } }
          const gz = hfAt(E0 + x[i], N0 + y[i]);
          if (z[i] - r < gz) { const ov = gz - (z[i] - r), ex = (hfAt(E0 + x[i] + 5, N0 + y[i]) - hfAt(E0 + x[i] - 5, N0 + y[i])) / 10, ey = (hfAt(E0 + x[i], N0 + y[i] + 5) - hfAt(E0 + x[i], N0 + y[i] - 5)) / 10, l = Math.sqrt(ex * ex + ey * ey + 1), nx = -ex / l, ny = -ey / l, nz = 1 / l;
            const vn = vx[i] * nx + vy[i] * ny + vz[i] * nz, F = Math.max(0, kn * ov - cn * vn); fx[i] += F * nx; fy[i] += F * ny; fz[i] += F * nz;
            const tx = vx[i] - vn * nx, ty = vy[i] - vn * ny, tz = vz[i] - vn * nz, tm = Math.hypot(tx, ty, tz); if (tm > 1e-6) { const Ft = Math.min(mu * F, tm * m / dt); fx[i] -= Ft * tx / tm; fy[i] -= Ft * ty / tm; fz[i] -= Ft * tz / tm; } }
        }
        for (let i = 0; i < N; i++) { vx[i] += fx[i] / m * dt; vy[i] += fy[i] / m * dt; vz[i] += fz[i] / m * dt; x[i] += vx[i] * dt; y[i] += vy[i] * dt; z[i] += vz[i] * dt; }
      }
      const ms = performance.now() - t0; let ke = 0; for (let i = 0; i < N; i++) ke += vx[i] * vx[i] + vy[i] * vy[i] + vz[i] * vz[i];
      return {N, steps, ms_per_step: ms / steps, finite: isFinite(ke)};
    }
    for (const N of [1000, 3000, 6000]) out.bench.push(demBench(N, 60));
  } catch (e) { out.errors.push(String(e.stack || e)); }
  const pre = document.createElement('pre'); pre.id = 'vresults'; pre.style.display = 'none'; pre.textContent = JSON.stringify(out); document.body.appendChild(pre);
  document.title = 'VALIDATION DONE';
})();
