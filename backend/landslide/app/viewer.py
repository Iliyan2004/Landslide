"""Builds the standalone Mapbox 3D scene for a physics run from SAILAB's own viewer assets (copied under static/viewer,
unmodified), patched at build time for debris flow: earth-tone palette, wording, quantised frame decoding."""
from __future__ import annotations
import base64, json, os
from datetime import datetime, timedelta
import numpy as np
from pyproj import Transformer

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "viewer")
DEBRIS_CURVE = {"depths": [0, 0.3, 1.0, 2.0, 4.0], "damage": [0, 0.05, 0.20, 0.55, 1.0]}   # = fragility damage ratios, burial floors
RISK_BANDS = [["low", 0.75], ["moderate", 1.25], ["significant", 2.00], ["extreme", float("inf")]]
SIZE_WARN = 150_000_000


def _asset(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


def _b64(a):
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode("ascii")


PATCHES_JS = [
    ("const DEPTH = W ? b64f32(W.depthB64) : null;",
     "function deq8(s, sc, signed) { const u = Uint8Array.from(atob(s), c => c.charCodeAt(0)); const o = new Float32Array(u.length);\n"
     "  if (signed) { const i8 = new Int8Array(u.buffer); for (let k = 0; k < o.length; k++) o[k] = i8[k] * sc / 127; } else { for (let k = 0; k < o.length; k++) o[k] = u[k] * sc / 255; } return o; }\n"
     "const DEPTH = W ? (W.depthQ8B64 ? deq8(W.depthQ8B64, W.depthScale, false) : b64f32(W.depthB64)) : null;"),
    ("const VX = (W && W.vxB64) ? b64f32(W.vxB64) : null;", "const VX = (W && W.vxQ8B64) ? deq8(W.vxQ8B64, W.vScale, true) : ((W && W.vxB64) ? b64f32(W.vxB64) : null);"),
    ("const VY = (W && W.vyB64) ? b64f32(W.vyB64) : null;", "const VY = (W && W.vyQ8B64) ? deq8(W.vyQ8B64, W.vScale, true) : ((W && W.vyB64) ? b64f32(W.vyB64) : null);"),
    ("linear-gradient(90deg,#3373f2,#f2c74d 50%,#ff5926)", "linear-gradient(90deg,#2a3885,#1a9eb8 25%,#f5db43 50%,#f57520 75%,#8c0a1a)"),
    ("linear-gradient(90deg,#73bdff,#4c9dff 35%,#1f48c9 70%,#0a1a78)", "linear-gradient(90deg,#e6c391,#c28a4a 35%,#7d4a1d 70%,#3a1f0a)"),
    ("#4c9dff", "#d9904a"), ("rgba(76,157,255,0.2)", "rgba(217,144,74,0.2)"),
    ("Water speed from the solver’s own velocity output", "Flow speed from the solver’s own velocity output"),
    ("Deepest water reached at each point during the event", "Deepest debris reached at each point during the event"),
    ("'Flooded area  '", "'Affected area  '"), (" ha flooded<br>", " ha affected<br>"), (" m³ on the surface'", " m³ of debris in motion or deposited'"),
    ("flood_3d.png", "landslide_3d.png"), ("flood_animation.mp4", "landslide_animation.mp4"),
]
QUAKE_JS = r'''
// ---- earthquake layers: shaking (PGA) map, fault rupture, epicentre, expanding wavefronts (time-scaled for visibility), brief ground shake
const QK = DATA.quake || null;
const QS = {pgaUrl: null};
function pgaRamp(t) { const st = [[0, [255, 255, 204]], [0.12, [161, 218, 180]], [0.3, [254, 217, 118]], [0.55, [240, 59, 32]], [1, [110, 0, 40]]]; for (let i = 1; i < st.length; i++) if (t <= st[i][0]) { const a = st[i - 1], b = st[i], k = (t - a[0]) / (b[0] - a[0]); return a[1].map((x, j) => Math.round(x + (b[1][j] - x) * k)); } return st[st.length - 1][1]; }
function buildPgaUrl() {
  const q = Uint8Array.from(atob(QK.pgaQ8B64), c => c.charCodeAt(0)), c = document.createElement('canvas'); c.width = W.ncols; c.height = W.nrows; const g = c.getContext('2d'), im = g.createImageData(W.ncols, W.nrows);
  for (let i = 0; i < q.length; i++) { if (!q[i]) continue; const col = pgaRamp(q[i] / 255); im.data[4 * i] = col[0]; im.data[4 * i + 1] = col[1]; im.data[4 * i + 2] = col[2]; im.data[4 * i + 3] = 215; }
  g.putImageData(im, 0, 0); const big = document.createElement('canvas'); big.width = W.ncols * 4; big.height = W.nrows * 4; const bg = big.getContext('2d'); bg.imageSmoothingEnabled = true; bg.drawImage(c, 0, 0, big.width, big.height); return big.toDataURL('image/png');
}
function ringPoly(cx, cy, rm, n) { const out = [], kx = 111320 * Math.cos(cy * Math.PI / 180), ky = 110540; for (let i = 0; i <= n; i++) { const a = i / n * 2 * Math.PI; out.push([cx + rm * Math.cos(a) / kx, cy + rm * Math.sin(a) / ky]); } return out; }
function addQuakeLayers() {
  if (!QK || map.getSource('q-pga')) return;
  const b = DATA.bbox, coords = [[b[0], b[3]], [b[2], b[3]], [b[2], b[1]], [b[0], b[1]]];
  if (QK.pgaQ8B64) { map.addSource('q-pga', {type: 'image', url: buildPgaUrl(), coordinates: coords}); map.addLayer({id: 'q-pga-layer', type: 'raster', source: 'q-pga', paint: {'raster-opacity': 0.85, 'raster-fade-duration': 0}, layout: {visibility: 'none'}}); }
  map.addSource('q-rupt', {type: 'geojson', data: {type: 'Feature', geometry: {type: 'LineString', coordinates: QK.rupture.length > 1 ? QK.rupture : [QK.rupture[0], QK.rupture[0]]}}});
  map.addLayer({id: 'q-rupt-glow', type: 'line', source: 'q-rupt', paint: {'line-color': '#ff3b30', 'line-width': 9, 'line-opacity': 0.35, 'line-blur': 5}});
  map.addLayer({id: 'q-rupt-line', type: 'line', source: 'q-rupt', paint: {'line-color': '#ff6a3d', 'line-width': 2.6}});
  map.addSource('q-epi', {type: 'geojson', data: {type: 'Feature', geometry: {type: 'Point', coordinates: QK.epi}}});
  map.addLayer({id: 'q-epi-layer', type: 'circle', source: 'q-epi', paint: {'circle-radius': 7, 'circle-color': '#ff3b30', 'circle-stroke-color': '#fff', 'circle-stroke-width': 2}});
  map.addSource('q-wave', {type: 'geojson', data: {type: 'FeatureCollection', features: []}});
  map.addLayer({id: 'q-wave-layer', type: 'line', source: 'q-wave', paint: {'line-color': '#ffd27a', 'line-width': ['get', 'w'], 'line-opacity': ['get', 'o'], 'line-blur': 1.5}});
}
function applyQuakeVisibility() { if (map.getLayer('q-pga-layer')) map.setLayoutProperty('q-pga-layer', 'visibility', ui.mode === 'shake' ? 'visible' : 'none'); }
const QW = {k: -1};
function updateQuake(simSec, loopT) {
  if (!QK || !map.getSource('q-wave')) return;
  const dt = simSec - QK.time_s, WAVE_LOOP = 0.09, fr = (loopT - (QK.loopT0 !== undefined ? QK.loopT0 : (QK.loopT0 = Math.max(0, (QK.time_s - W.simStartS) / (W.saveIntMin * 60 * (nFrames - 1)))))) / WAVE_LOOP;
  const k = Math.round(fr * 60); if (k === QW.k) return; QW.k = k;
  const diag = Math.hypot((DATA.bbox[2] - DATA.bbox[0]) * 111320 * Math.cos(QK.epi[1] * Math.PI / 180), (DATA.bbox[3] - DATA.bbox[1]) * 110540) + 4000, feats = [];
  if (fr >= 0 && fr <= 1.4) for (let i = 0; i < 4; i++) { const f = fr - i * 0.11; if (f < 0 || f > 1) continue; feats.push({type: 'Feature', properties: {w: 6.5 * (1 - f) + 1.5, o: Math.min(1, 1.15 * (1 - f) + 0.1)}, geometry: {type: 'LineString', coordinates: ringPoly(QK.epi[0], QK.epi[1], f * diag * 1.5, 96)}}); }
  map.getSource('q-wave').setData({type: 'FeatureCollection', features: feats});
  if (fr >= 0 && fr < 0.32 && !map.isMoving()) { const amp = 1.1 * (1 - fr / 0.32) * Math.sin(fr * 150); map.setBearing(map.getBearing() + amp * 0.35); }
}
'''
MASS_JS = r'''
// ---- 3D debris body: a displaced surface mesh (three.js custom layer) standing on Mapbox's own terrain, with a per-pixel rubble material in metres
const MASS = {on: true};
const HAS_MESH = (typeof THREE !== 'undefined') && W && !W.colorStops && DEPTH;
const MESH = {obj: null, elev: null, nElev: 0, key: -1, o: null, scale: 1, last: 0, lastElevT: 0, ex: 1.5};
function meshOrigin() { const b = DATA.bbox, c = mapboxgl.MercatorCoordinate.fromLngLat([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2], 0); MESH.o = c; MESH.scale = c.meterInMercatorCoordinateUnits(); }
function vertLL(r, c) { const b = DATA.bbox; return [b[0] + (c + 0.5) / W.ncols * (b[2] - b[0]), b[3] - (r + 0.5) / W.nrows * (b[3] - b[1])]; }
function refreshElev() {
  const nc = W.ncols, nr = W.nrows; let ok = 0;
  if (!MESH.elev) MESH.elev = new Float32Array(nc * nr);
  for (let r = 0; r < nr; r++) for (let c = 0; c < nc; c++) {
    const e = map.queryTerrainElevation(vertLL(r, c), {exaggerated: true});
    if (e !== null && e !== undefined) { MESH.elev[r * nc + c] = e; ok++; }
  }
  MESH.nElev = ok; MESH.key = -1; MESH.lastElevT = performance.now();
}
function buildMesh() {
  const nc = W.ncols, nr = W.nrows, n = nc * nr, g = new THREE.BufferGeometry();
  const pos = new Float32Array(n * 3), nrm = new Float32Array(n * 3), dep = new Float32Array(n), spd = new Float32Array(n), idx = [];
  const o = MESH.o, s = MESH.scale;
  for (let r = 0; r < nr; r++) for (let c = 0; c < nc; c++) {
    const i = r * nc + c, m = mapboxgl.MercatorCoordinate.fromLngLat(vertLL(r, c), 0);
    pos[3 * i] = (m.x - o.x) / s; pos[3 * i + 1] = -(m.y - o.y) / s; pos[3 * i + 2] = 0; nrm[3 * i + 2] = 1;
    if (r < nr - 1 && c < nc - 1) { idx.push(i, i + nc, i + 1, i + 1, i + nc, i + nc + 1); }
  }
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('normal', new THREE.BufferAttribute(nrm, 3));
  g.setAttribute('aDepth', new THREE.BufferAttribute(dep, 1)); g.setAttribute('aSpeed', new THREE.BufferAttribute(spd, 1)); g.setIndex(idx);
  const mat = new THREE.ShaderMaterial({transparent: true, depthWrite: true, side: THREE.DoubleSide,
    uniforms: {uMaxD: {value: Math.max(W.maxDepth, 0.5)}, uL: {value: new THREE.Vector3(-0.5, -0.45, 0.74)}, uTime: {value: 0}},
    vertexShader: `attribute float aDepth; attribute float aSpeed; varying float vD; varying float vS; varying vec3 vN; varying vec2 vXY;
      void main(){ vD = aDepth; vS = aSpeed; vN = normal; vXY = position.xy; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `precision highp float; varying float vD; varying float vS; varying vec3 vN; varying vec2 vXY; uniform float uMaxD; uniform vec3 uL; uniform float uTime;
      float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453); }
      float vnoise(vec2 p){ vec2 i=floor(p), f=fract(p); f=f*f*(3.-2.*f); return mix(mix(hash(i),hash(i+vec2(1,0)),f.x), mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x), f.y); }
      void main(){
        if (vD < 0.05) discard;
        vec2 p = vXY;
        float g1 = vnoise(p*1.1), g2 = vnoise(p*3.4), g3 = vnoise(p*0.23), g4 = vnoise(p*8.0);
        vec3 n = normalize(vN);
        float rough = 0.35 + 0.6*smoothstep(0.0, 1.5, vD);
        n = normalize(n + vec3(vnoise(p*1.6+3.)-0.5, vnoise(p*1.6+9.)-0.5, 0.0)*rough + vec3(g2-0.5, vnoise(p*3.4+5.)-0.5, 0.)*0.30);
        float diff = max(dot(n, normalize(uL)), 0.0);
        float rest = 1.0 - smoothstep(0.30, 1.2, vS);
        float thin = 1.0 - smoothstep(0.0, 0.30*uMaxD + 0.4, vD);
        vec3 wet = vec3(0.17,0.115,0.08), dry = vec3(0.70,0.60,0.47), rock = vec3(0.44,0.43,0.42);
        vec3 base = mix(wet, dry, clamp(rest*0.85 + thin*0.30, 0., 1.));
        float big = step(0.74, vnoise(p*0.42+7.1)), med = step(0.70, vnoise(p*1.25+2.7));       // boulders (~3 m) and cobbles (~1 m)
        float rocky = clamp(big*0.85 + med*0.55, 0., 1.);
        base = mix(base, rock*(0.62 + 0.75*g2), rocky);
        base *= 0.78 + 0.34*g1 + 0.22*g3 + 0.07*g4;
        float crack = smoothstep(0.0, 0.10, abs(vnoise(p*0.7+3.3)-0.5)*2.0);
        base *= mix(1.0, 0.70 + 0.30*crack, rest);
        float hot = smoothstep(1.5, 9.0, vS) * (1.0-rest);
        vec3 col = base*(0.38 + 0.95*diff) + vec3(1.0,0.55,0.20)*hot*0.34;
        col = mix(col, col*vec3(1.08,1.05,1.0)+0.04, rest*thin*0.5);                              // pale dust on thin settled edges
        float a = smoothstep(0.05, 0.22, vD);
        gl_FragColor = vec4(col, a);
      }`});
  const mesh = new THREE.Mesh(g, mat); mesh.frustumCulled = false; return mesh;
}
function updateMesh(seg, mix) {
  if (!MASS.on || !MESH.obj || ui.mode === 'terrain' || ui.mode === 'speed') return;
  const now = performance.now();
  if (MESH.nElev < W.ncols * W.nrows * 0.9 ? (now - MESH.lastElevT > 1200) : (now - MESH.lastElevT > 4000 && map.isMoving() === false && MESH.key !== -3)) { refreshElev(); }
  const key = (ui.mode === 'max' ? -2 : seg * 16 + Math.round(mix * 15)); if (key === MESH.key) return; MESH.key = key;
  const nc = W.ncols, nr = W.nrows, g = MESH.obj.geometry, pos = g.attributes.position.array, nrm = g.attributes.normal.array, dep = g.attributes.aDepth.array, spd = g.attributes.aSpeed.array;
  const A = seg * cellCount, B = Math.min(seg + 1, nFrames - 1) * cellCount, mx = ui.mode === 'max', el = MESH.elev || new Float32Array(cellCount), ex = MESH.ex;
  const z = MESH.z || (MESH.z = new Float32Array(cellCount));
  for (let i = 0; i < cellCount; i++) {
    const d = mx ? MAXD_ARR[i] : DEPTH[A + i] + (DEPTH[B + i] - DEPTH[A + i]) * mix;
    dep[i] = d;
    let sp = 0; if (VX && !mx) { const vx = VX[A + i] + (VX[B + i] - VX[A + i]) * mix, vy = VY[A + i] + (VY[B + i] - VY[A + i]) * mix; sp = Math.hypot(vx, vy); }
    spd[i] = sp; z[i] = el[i] + (d > 0.05 ? d * ex + 0.2 : 0);
    pos[3 * i + 2] = z[i];
  }
  const cx = cellX || 30, cy = cellY || 30;
  for (let r = 0; r < nr; r++) for (let c = 0; c < nc; c++) {
    const i = r * nc + c, l = c > 0 ? i - 1 : i, rr = c < nc - 1 ? i + 1 : i, u = r > 0 ? i - nc : i, d2 = r < nr - 1 ? i + nc : i;
    let nx = -(z[rr] - z[l]) / (2 * cx), ny = (z[d2] - z[u]) / (2 * cy);                 // rows run south: +row = -north
    const inv = 1 / Math.hypot(nx, ny, 1); nrm[3 * i] = nx * inv; nrm[3 * i + 1] = ny * inv; nrm[3 * i + 2] = inv;
  }
  g.attributes.position.needsUpdate = true; g.attributes.normal.needsUpdate = true; g.attributes.aDepth.needsUpdate = true; g.attributes.aSpeed.needsUpdate = true;
  map.triggerRepaint();
}
const meshLayer = {id: 'debris-mesh', type: 'custom', renderingMode: '3d',
  onAdd(m, gl) { this.camera = new THREE.Camera(); this.scene = new THREE.Scene(); this.renderer = new THREE.WebGLRenderer({canvas: m.getCanvas(), context: gl, antialias: true}); this.renderer.autoClear = false;
    if (!MESH.o) meshOrigin(); if (!MESH.obj) MESH.obj = buildMesh(); this.scene.add(MESH.obj); refreshElev(); },
  render(gl, matrix) { if (!MASS.on || ui.mode === 'terrain' || ui.mode === 'speed') return; const o = MESH.o, s = MESH.scale;
    const m = new THREE.Matrix4().fromArray(matrix), l = new THREE.Matrix4().makeTranslation(o.x, o.y, 0).scale(new THREE.Vector3(s, -s, s));
    this.camera.projectionMatrix = m.multiply(l); this.renderer.resetState(); this.renderer.render(this.scene, this.camera); },
  onRemove() { if (this.scene && MESH.obj) this.scene.remove(MESH.obj); }};
function addMassLayers() { if (!HAS_MESH || map.getLayer('debris-mesh')) return; map.addLayer(meshLayer); }
function applyMassVisibility() { MESH.key = -1; map.triggerRepaint(); }
function updateMass(seg, mix) { if (HAS_MESH) updateMesh(seg, mix); }
'''
EXTRA_JS_PATCHES = [
    ("const UP = W ? Math.max(1, Math.min(4, Math.floor(1600 / Math.max(W.ncols, W.nrows)))) : 1;", "const UP = W ? Math.max(1, Math.min(10, Math.floor(1800 / Math.max(W.ncols, W.nrows)))) : 1;"),
    ("if (W && !VX) { $('cardSpeed')", "if (QK) { const cs = $('cardShake'); if (cs) cs.style.display = ''; }\nif (W && !VX) { $('cardSpeed')"),
    ("function applyFlowVisibility() {", "function applyFlowVisibility() {\n  if (typeof applyMassVisibility === 'function') applyMassVisibility();\n  if (typeof applyQuakeVisibility === 'function') applyQuakeVisibility();"),
    ("  applyLabels(); applyWaterPaint(); applyFlowVisibility();\n  bColorCache.fill(''); rColorCache.fill('');", "  addMassLayers(); if (typeof addQuakeLayers === 'function') addQuakeLayers();\n  applyLabels(); applyWaterPaint(); applyFlowVisibility();\n  bColorCache.fill(''); rColorCache.fill('');"),
    ("  setFloodFrame(seg, mixFrac);\n  if (HAS_ANIM) {", "  setFloodFrame(seg, mixFrac);\n  if (W && DEPTH) updateMass(seg, mixFrac);\n  if (QK) updateQuake(t * totalSimMin * 60 + (W.simStartS || 0), t);\n  if (HAS_ANIM) {"),
    ("$('pillBuildings').addEventListener('click',", QUAKE_JS + MASS_JS + "if ($('pillMass')) { if (!HAS_MESH) $('pillMass').style.display = 'none'; else $('pillMass').addEventListener('click', (e) => { MASS.on = !MASS.on; e.currentTarget.classList.toggle('on', MASS.on); applyMassVisibility(); }); }\n$('pillBuildings').addEventListener('click',"),
    ("const LOOP_SECONDS = 9.0;", "const LOOP_SECONDS = 24.0;"),
    ("function tickBody(now) {\n  if (lastNow === null) lastNow = now;", "function tickBody(now) {\n  tick._n = (tick._n || 0) + 1; if (!tick._ready && tick._n > 90) { tick._ready = true; document.documentElement.setAttribute('data-ready', '1'); }\n  if (lastNow === null) lastNow = now;"),
    ("console.warn('water shader:', gl.getShaderInfoLog(s)); return null;", "console.warn('water shader:', gl.getShaderInfoLog(s)); document.documentElement.setAttribute('data-shader-err', String(gl.getShaderInfoLog(s)).slice(0, 700)); return null;"),
    ("map.on('load', () => {\n  addSceneSources(); resetView();", "map.on('error', (e) => { document.documentElement.setAttribute('data-map-err', String((e && e.error && e.error.message) || e).slice(0, 400)); });\nmap.on('load', () => {\n  addSceneSources(); resetView();"),
    ("if (!tick._warned) { tick._warned = true; console.warn('frame error (continuing):', e); }", "if (!tick._warned) { tick._warned = true; console.warn('frame error (continuing):', e); document.documentElement.setAttribute('data-frame-err', String((e && e.stack) || e).slice(0, 600)); }"),
    ("gl.uniform1i(U('uDA'), 0); gl.uniform1i(U('uDB'), 1); gl.uniform1i(U('uVA'), 2); gl.uniform1i(U('uVB'), 3);",
     "gl.uniform1i(U('uDA'), 0); gl.uniform1i(U('uDB'), 1); gl.uniform1i(U('uVA'), 2); gl.uniform1i(U('uVB'), 3);\n"
     "  function mk1(unit, data, filt) { const t = gl.createTexture(); gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_2D, t);\n"
     "    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filt); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filt);\n"
     "    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);\n"
     "    gl.texImage2D(gl.TEXTURE_2D, 0, gl.R8, nc, nr, 0, gl.RED, gl.UNSIGNED_BYTE, data); return t; }\n"
     "  const dec8 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));\n"
     "  gl.uniform1f(U('uHasTF'), 0); gl.uniform1f(U('uHasBC'), 0); gl.uniform1f(U('uCell'), W.cellsizeM || 30); gl.uniform1f(U('uBCmax'), W.bedScale || 1);\n"
     "  if (W.relFrameQ8B64) { mk1(4, dec8(W.relFrameQ8B64), gl.NEAREST); gl.uniform1i(U('uTF'), 4); gl.uniform1f(U('uHasTF'), 1); }\n"
     "  if (W.bedChangeQ8B64) { mk1(5, dec8(W.bedChangeQ8B64), gl.LINEAR); gl.uniform1i(U('uBC'), 5); gl.uniform1f(U('uHasBC'), 1); }\n"
     "  if (!W.relFrameQ8B64) { mk1(4, new Uint8Array(cellCount), gl.NEAREST); gl.uniform1i(U('uTF'), 4); }\n"
     "  if (!W.bedChangeQ8B64) { mk1(5, new Uint8Array(cellCount).fill(128), gl.LINEAR); gl.uniform1i(U('uBC'), 5); }"),
    ("setMode(m) { modeMax = (m === 'max'); segA = segB = -1; gl.uniform1f(U('uMode'), m === 'speed' ? 2 : 0); },",
     "setMode(m) { modeMax = (m === 'max'); segA = segB = -1; gl.uniform1f(U('uMode'), m === 'speed' ? 2 : (m === 'terrain' ? 3 : 0)); },"),
    ("gl.uniform1f(U('uTime'), performance.now() / 1000);", "gl.uniform1f(U('uTime'), performance.now() / 1000); gl.uniform1f(U('uFrame'), seg + (modeMax ? 0 : mixFrac));"),
    ("if (!flowCanvas || !ui.flowOn || ui.mode === 'max') return;", "if (!flowCanvas || !ui.flowOn || ui.mode === 'max' || ui.mode === 'terrain') return;"),
    ("(ui.flowOn || ui.mode === 'paths') && ui.mode !== 'max' ? 'visible' : 'none'", "(ui.flowOn || ui.mode === 'paths') && ui.mode !== 'max' && ui.mode !== 'terrain' ? 'visible' : 'none'"),
    ("    if (ui.mode === 'speed') {\n", "    if (ui.mode === 'terrain') {\n      bar.style.background = 'linear-gradient(90deg,#0f3a78,#7fb0dc 30%,#f0dcb0 50%,#b98a50 72%,#4a2408)';\n"
     "      const bs = W.bedScale || 1; lbl.innerHTML = ['-' + bs.toFixed(1) + ' m', '0', '+' + bs.toFixed(1) + ' m'].map(s => '<span>' + s + '</span>').join('');\n"
     "      $('legendNote').textContent = 'Net change of the ground: blue = scar or scour (lost), brown = deposit (gained)'; return;\n    }\n    if (ui.mode === 'speed') {\n"),
    ("'rgba(255,255,255,' + (0.30 + 0.65 * s).toFixed(2) + ')'", "'rgba(255,238,205,' + (0.28 + 0.6 * s).toFixed(2) + ')'"),
    ("const ts = $('timeSlider');", "const ts = $('timeSlider');\n"
     "const _qp = new URLSearchParams(location.search);\n"
     "if (_qp.has('t')) { elapsedSeconds = Math.max(0, Math.min(1, parseFloat(_qp.get('t')))) * LOOP_SECONDS; playing = false; $('playPauseBtn').innerHTML = '&#9654;'; }\n"
     "if (_qp.get('panel') === '0') { $('panel').classList.add('collapsed'); document.body.classList.add('panel-collapsed'); }\n"
     "if (_qp.get('mode')) setTimeout(() => { const c = document.querySelector('.card[data-mode=\"' + _qp.get('mode') + '\"]'); if (c) c.click(); }, 1800);\n"
     "if (_qp.get('cam')) { const cm = _qp.get('cam').split(',').map(Number); map.on('load', () => setTimeout(() => map.jumpTo(Object.assign({zoom: cm[0], pitch: cm[1], bearing: cm[2]}, cm.length > 4 ? {center: [cm[3], cm[4]]} : {})), 2500)); }"),
    ("function resetView() { const b = DATA.bbox; map.fitBounds([[b[0], b[1]], [b[2], b[3]]], {padding: {top: 80, bottom: 220, left: 340, right: 80}, pitch: 60, bearing: -17, duration: 0}); }",
     "function resetView() { const b = DATA.bbox, c = DATA.cam || {}; map.fitBounds([[b[0], b[1]], [b[2], b[3]]], {padding: {top: 80, bottom: 220, left: 340, right: 80}, pitch: (c.pitch != null ? c.pitch : 60), bearing: (c.bearing != null ? c.bearing : -17), duration: 0}); }"),
]
PATCHES_HTML = [
    ("Fine-tune water and terrain", "Fine-tune flow and terrain"), ("click the water", "click the flow"),
    ("Flooded area", "Affected area"), ("Deepest water", "Deepest flow"), ("Water on surface", "Debris volume"),
    ('<button class="pill on" id="pillFlow">Flow lines</button>', '<button class="pill on" id="pillFlow">Flow lines</button>\n      <button class="pill on" id="pillMass">3D mass</button>'),
    ("Depth over time", "Debris in motion"), ("<span>Maximum depth</span>", "<span>Peak debris depth</span>"),
    ('<button class="card c-paths" data-mode="paths" id="cardPaths"><span>Flow paths</span></button>',
     '<button class="card c-paths" data-mode="paths" id="cardPaths"><span>Flow paths</span></button>\n        <button class="card c-terrain" data-mode="terrain" id="cardTerrain"><span>Terrain change</span></button>\n        <button class="card c-shake" data-mode="shake" id="cardShake" style="display:none"><span>Ground shaking</span></button>'),
]
EXTRA_CSS = (".c-shake{background:radial-gradient(circle at 50% 50%,#6e0028,#f03b20 35%,#fed976 60%,transparent 75%),linear-gradient(135deg,#2a1a1a,#120a0a)}"
             ".c-depth{background:radial-gradient(circle at 35% 65%,#8a6a46,transparent 55%),linear-gradient(135deg,#2a2218,#15110b)}"
             ".c-max{background:radial-gradient(circle at 60% 60%,#5a3a1e,transparent 60%),linear-gradient(135deg,#2c2418,#17120c)}"
             ".c-terrain{background:linear-gradient(100deg,#1b4d8f 0%,#9fc6e6 30%,#f0dcb0 50%,#b98a50 72%,#4a2408 100%)}")


def build(out_path, title, aoi_geom, token, epsg, affine, crop, H, VX, VY, frame_t, stats, series, t0_s,
          buildings, roads, dx, legend_html="", z_exag=1.3, tfail_s=None, bedchange=None, quake=None):
    """H/VX/VY: (T, nr, nc) float16 frames ALREADY CROPPED; crop=(r0,r1,c0,c1) locates them on the full grid. frame_t seconds since the start."""
    r0, r1, c0, c1 = crop
    Hc = H.astype("float32")
    T, nr, nc = Hc.shape
    maxD = float(max(Hc.max(), 0.5))
    tr = Transformer.from_crs(epsg, 4326, always_xy=True)
    xs = [affine * (c0, r0), affine * (c1, r0), affine * (c1, r1), affine * (c0, r1)]
    ll = [tr.transform(x, y) for x, y in xs]
    bbox = [min(p[0] for p in ll), min(p[1] for p in ll), max(p[0] for p in ll), max(p[1] for p in ll)]
    inv = ~affine
    to_cell = Transformer.from_crs(4326, epsg, always_xy=True)
    vref = float(max(np.percentile(np.abs(VX).astype("float32"), 99.9), np.percentile(np.abs(VY).astype("float32"), 99.9), 1.0))
    q8 = np.clip(np.rint(Hc / maxD * 255), 0, 255).astype("uint8")
    vq = lambda A: np.clip(np.rint(A.astype("float32") / vref * 127), -127, 127).astype("int8")

    def traj(rr, cc):
        rr, cc = rr - r0, cc - c0
        if not (1 <= rr < nr - 1 and 1 <= cc < nc - 1):
            return None
        a = H[:, rr - 1:rr + 2, cc - 1:cc + 2].astype("float32").reshape(T, -1).max(1)
        return [round(float(x), 2) for x in a] if a.max() > 0.05 else None

    bf, n_aff = [], 0
    for b in sorted(buildings, key=lambda b: -(b.get("dmg", 0))):
        if "rr" not in b:
            continue
        d = traj(b["rr"], b["cc"])
        if d is None and len(bf) > 4000:
            continue
        n_aff += d is not None
        bf.append({"coords_lonlat": b["coords_lonlat"], "height_m": b["height_m"], "depths": d})
        if len(bf) >= 8000:
            break
    rf = []
    for rd in roads:
        pts = rd["coords_lonlat"]; mid = pts[len(pts) // 2]
        x, y = to_cell.transform(*mid); cc, rr = inv * (x, y)
        d = traj(int(rr), int(cc))
        rf.append({"coords_lonlat": pts, "depths": d, "speeds": [0.0] * T if d else None})
    rel_q = bed_q = None
    bed_scale = 1.0
    if tfail_s is not None:
        tf = tfail_s
        dtf = float(frame_t[1] - frame_t[0])
        idx = np.floor((tf - float(frame_t[0])) / dtf)
        rel_q = np.where(np.isfinite(tf), np.clip(idx, 0, T - 1) + 1, 0).astype("uint8")          # release frame + 1 (0 = never failed)
    if bedchange is not None:
        bc = np.nan_to_num(bedchange).astype("float32")
        bed_scale = float(max(np.percentile(np.abs(bc[np.abs(bc) > 0.05]), 99) if (np.abs(bc) > 0.05).any() else 1.0, 0.5))
        bed_q = (np.clip(np.rint(bc / bed_scale * 127), -127, 127) + 128).astype("uint8")
    cam = {"pitch": 58.0, "bearing": -17.0}
    if tfail_s is not None and bedchange is not None:
        src = np.argwhere(np.isfinite(tfail_s)); dep = np.argwhere(np.nan_to_num(bedchange) > 0.5)
        if len(src) >= 3 and len(dep) >= 3:
            (rs, cs), (rd, cd) = src.mean(0), dep.mean(0)
            e, n = (cs - cd), -(rs - rd)                                  # from the deposit up toward the source (east, north)
            if np.hypot(e, n) > 4:
                cam["bearing"] = float(np.degrees(np.arctan2(e, n)))       # the camera looks UP the slope from below: the mass runs toward the viewer
    qpay = None
    if quake:
        pg = quake.get("pga")
        pm = float(max(np.nanmax(pg), 0.05)) if pg is not None and np.size(pg) else 0.0
        pq = (np.where(np.isfinite(pg) & (pg > 0), np.maximum(np.clip(np.rint(pg / pm * 255), 0, 255), 1), 0).astype("uint8") if pm else None)
        qpay = {"epi": quake["epi"], "rupture": quake["rupture"], "mag": quake["mag"], "time_s": quake["time_s"], "pgaQ8B64": _b64(pq) if pq is not None else None, "pgaMax": pm}
    start_iso, rain_t, rain_r = None, None, None
    if series:
        if series.get("start_iso"):
            try:
                s0 = datetime.fromisoformat(series["start_iso"].replace("Z", "+00:00"))
                start_iso = (s0 + timedelta(seconds=float(t0_s))).isoformat()
            except ValueError:
                pass
        th = np.asarray(series["times_h"], float) - t0_s / 3600.0
        rr_ = np.asarray(series["rate_mm_h"], float)
        keep = th > -1e-9
        rain_t = [0.0] + [round(float(x), 4) for x in th[keep]]
        rain_r = [float(rr_[keep][0]) if keep.any() else 0.0] + [round(float(x), 3) for x in rr_[keep]]
    water = {"depthQ8B64": _b64(q8), "depthScale": maxD, "vxQ8B64": _b64(vq(VX)), "vyQ8B64": _b64(vq(VY)), "vScale": vref,
             "nFrames": int(T), "nrows": int(nr), "ncols": int(nc), "saveIntMin": float((frame_t[1] - frame_t[0]) / 60.0),
             "dryThresh": 0.1, "maxDepth": maxD, "cellsizeM": float(dx), "durationHr": round(float((frame_t[-1] - frame_t[0]) / 3600.0), 1),
             "peakMmHr": float(max(series["rate_mm_h"])) if series else 0.0, "startTimeIso": start_iso,
             "rainTimesHr": rain_t, "rainRatesMmHr": rain_r,
             "relFrameQ8B64": _b64(rel_q) if rel_q is not None else None, "bedChangeQ8B64": _b64(bed_q) if bed_q is not None else None, "bedScale": bed_scale, "simStartS": float(frame_t[0])}
    payload = {"bbox": bbox, "center": [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2], "aoiGeom": aoi_geom,
               "buildings": {"type": "FeatureCollection", "features": [{"type": "Feature", "id": i, "properties": {"height_m": f["height_m"], "depths": f["depths"]},
                             "geometry": {"type": "Polygon", "coordinates": [f["coords_lonlat"]]}} for i, f in enumerate(bf)]},
               "roads": {"type": "FeatureCollection", "features": [{"type": "Feature", "id": i, "properties": {"depths": f["depths"], "speeds": f["speeds"]},
                         "geometry": {"type": "LineString", "coordinates": f["coords_lonlat"]}} for i, f in enumerate(rf)]},
               "water": water, "cam": cam, "quake": qpay, "huizingaBuiltUp": DEBRIS_CURVE, "riskBands": RISK_BANDS, "zExag": z_exag, "mapboxToken": token}
    js = _asset("mapbox3d_app.js")
    i0 = js.index("  const FS = `#version 300 es"); i1 = js.index("  function sh(type, src) {")
    js = js[:i0] + "  const FS = `" + _asset("debris_shader.glsl") + "`;\n" + js[i1:]          # whole water shader replaced by the debris material
    for a, b in EXTRA_JS_PATCHES:
        if a not in js:
            raise RuntimeError(f"viewer patch target missing (SAILAB viewer changed?): {a[:60]}")
        js = js.replace(a, b)
    for a, b in PATCHES_JS:
        if a not in js:
            raise RuntimeError(f"viewer patch target missing (SAILAB viewer changed?): {a[:50]}")
        js = js.replace(a, b)
    body = _asset("mapbox3d_body.html")
    for a, b in PATCHES_HTML:
        body = body.replace(a, b)
    body = body.replace("__TITLE__", title).replace("__ZEXAG__", f"{z_exag:.1f}").replace("__LEGEND__", legend_html or "").replace("__ABOUT_STYLE__", "" if legend_html else "display:none")
    pj = json.dumps(payload).replace("</", "<\\/")
    html = ("<!doctype html>\n<title>" + title + "</title>\n<meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<link href=\"https://api.mapbox.com/mapbox-gl-js/v3.6.0/mapbox-gl.css\" rel=\"stylesheet\">\n<style>\n" + _asset("mapbox3d_style.css") + "\n" + EXTRA_CSS + "\n</style>\n" + body +
            "\n<script src=\"https://unpkg.com/three@0.160.0/build/three.min.js\"></script>\n<script>window.addEventListener('error',function(e){document.documentElement.setAttribute('data-err',(e.message||'')+' @'+e.lineno+':'+e.colno)});</script>\n<script src=\"https://api.mapbox.com/mapbox-gl-js/v3.6.0/mapbox-gl.js\"></script>\n<script>\n" + js.replace("__PAYLOAD__", pj) + "\n</script>\n")
    with open(out_path, "w") as f:
        f.write(html)
    return {"bbox": bbox, "size_bytes": os.path.getsize(out_path), "buildings": len(bf), "buildings_hit": n_aff, "frames": int(T)}
