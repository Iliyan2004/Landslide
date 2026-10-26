// LANDLAB rockfall scene: individual rocks (flight, bounce, roll) with trails and dust over Mapbox terrain, plus reach / energy / bounce maps.
const DATA = __PAYLOAD__;
mapboxgl.accessToken = DATA.token;
const $ = (id) => document.getElementById(id);
const dec = (s) => Uint8Array.from(atob(s), c => c.charCodeAt(0));
const f32 = (s) => new Float32Array(dec(s).buffer);
const B = DATA.bbox, NC = DATA.ncols, NR = DATA.nrows, CELL = DATA.cell_m;
const R = DATA.rocks;                                                     // tracked rocks
const NREC = R.nrec, M = R.m, DT = R.dt, TMAX = NREC * DT;
const LON = f32(R.lonB64), LAT = f32(R.latB64), HGT = f32(R.hB64), SPD = f32(R.vB64), IMP = dec(R.impB64), STA = dec(R.stateB64), DIA = f32(R.diaB64);
const MASS = Array.from(DIA, d => 4 / 3 * Math.PI * Math.pow(d / 2, 3) * 2600);
const ui = {style: 'satellite', terrain: true, labels: false, buildings: true, trails: true, dust: true, exag: 1.4, mode: 'rocks', opacity: 0.8, size: 1.0, trail: 36, speed: 1, playing: true};
const STYLE_URLS = {dark: 'mapbox://styles/mapbox/dark-v11', light: 'mapbox://styles/mapbox/light-v11', satellite: 'mapbox://styles/mapbox/satellite-streets-v12',
  streets: 'mapbox://styles/mapbox/streets-v12', terrain: 'mapbox://styles/mapbox/outdoors-v12', night: 'mapbox://styles/mapbox/navigation-night-v1'};
const map = new mapboxgl.Map({container: 'map', style: STYLE_URLS.satellite, center: DATA.center, zoom: 14, pitch: 58, bearing: (DATA.cam && DATA.cam.bearing) || 0, antialias: true, preserveDrawingBuffer: true, maxPitch: 80});
map.addControl(new mapboxgl.NavigationControl({visualizePitch: true}), 'top-right');
map.on('error', (e) => document.documentElement.setAttribute('data-map-err', String((e && e.error && e.error.message) || e).slice(0, 300)));
window.addEventListener('error', (e) => document.documentElement.setAttribute('data-err', (e.message || '') + ' @' + e.lineno));
function srcCentre() { const f = DATA.sources.features; if (!f.length) return DATA.center; let x = 0, y = 0; f.forEach(q => { x += q.geometry.coordinates[0]; y += q.geometry.coordinates[1]; }); return [x / f.length, y / f.length]; }
function resetView() { if (DATA.sources.features.length) { const c = srcCentre(); map.jumpTo({center: [c[0], c[1] - 0.0035], zoom: 14.3, pitch: (DATA.cam && DATA.cam.pitch) || 60, bearing: (DATA.cam && DATA.cam.bearing) || 0}); return; } map.fitBounds([[B[0], B[1]], [B[2], B[3]]], {padding: {top: 80, bottom: 220, left: ui.panel ? 340 : 60, right: 80}, pitch: (DATA.cam && DATA.cam.pitch) || 58, bearing: (DATA.cam && DATA.cam.bearing) || 0, duration: 0}); }
// ---------- colour ramps -> overlay canvases
function ramp(stops, t) { t = Math.max(0, Math.min(1, t)); for (let i = 1; i < stops.length; i++) { if (t <= stops[i][0]) { const a = stops[i - 1], b = stops[i], k = (t - a[0]) / (b[0] - a[0] || 1); return a[1].map((v, j) => Math.round(v + (b[1][j] - v) * k)); } } return stops[stops.length - 1][1]; }
const RAMPS = {
  reach: [[0, [255, 245, 190]], [0.25, [253, 190, 90]], [0.55, [240, 100, 40]], [1, [140, 10, 20]]],
  energy: [[0, [250, 240, 160]], [0.3, [250, 180, 60]], [0.6, [220, 60, 40]], [0.85, [150, 20, 90]], [1, [60, 10, 100]]],
  bounce: [[0, [220, 235, 250]], [0.35, [120, 190, 220]], [0.7, [40, 110, 190]], [1, [20, 40, 120]]]};
const MAPS = {reach: {q: DATA.maps.reachB64, max: DATA.maps.reachMax, label: 'Share of released rocks that pass', unit: '%', scale: v => v * 100, log: false, sq: true},
  energy: {q: DATA.maps.energyB64, max: DATA.maps.energyMax, label: 'Peak translational energy', unit: 'kJ', log: true},
  bounce: {q: DATA.maps.bounceB64, max: DATA.maps.bounceMax, label: 'Peak bounce height above ground', unit: 'm', log: false}};
function mapCanvas(key) {
  const m = MAPS[key], q = dec(m.q), c = document.createElement('canvas'); c.width = NC; c.height = NR; const g = c.getContext('2d'), img = g.createImageData(NC, NR);
  for (let i = 0; i < NC * NR; i++) { const t = q[i] / 255; if (q[i] === 0) { img.data[4 * i + 3] = 0; continue; } const col = ramp(RAMPS[key], t); img.data[4 * i] = col[0]; img.data[4 * i + 1] = col[1]; img.data[4 * i + 2] = col[2]; img.data[4 * i + 3] = 235; }
  g.putImageData(img, 0, 0);
  const big = document.createElement('canvas'); big.width = NC * 4; big.height = NR * 4; const bg = big.getContext('2d'); bg.imageSmoothingEnabled = true; bg.imageSmoothingQuality = 'high'; bg.drawImage(c, 0, 0, big.width, big.height);
  return big.toDataURL('image/png');
}
const COORDS = [[B[0], B[3]], [B[2], B[3]], [B[2], B[1]], [B[0], B[1]]];
const CLS_COL = ['#f2d94e', '#f0883e', '#d93a2a', '#8a1230', '#5a1a8a'], CLS_LAB = ['< 10 kJ', '10 - 50 kJ', '50 - 300 kJ', '300 - 1000 kJ', '> 1000 kJ'];
// ---------- three.js custom layer: rocks, trails, dust
const HAS3 = typeof THREE !== 'undefined';
const S3 = {o: null, s: 1, rocks: null, trailGeo: null, dust: null, hist: null, histN: 0, lastT: -1, dustN: 0, dustT: [], mat: null};
function mercOrigin() { const c = mapboxgl.MercatorCoordinate.fromLngLat(DATA.center, 0); S3.o = c; S3.s = c.meterInMercatorCoordinateUnits(); }
function llToWorld(lon, lat, z) { const m = mapboxgl.MercatorCoordinate.fromLngLat([lon, lat], 0); return [(m.x - S3.o.x) / S3.s, -(m.y - S3.o.y) / S3.s, z]; }
const rockColor = new THREE.Color();
function energyColor(e, out) { const t = Math.min(1, Math.log10(1 + e / 1000) / Math.log10(1 + (DATA.stats.peakEnergyKj || 100))); const c = ramp(RAMPS.energy, t); return out.setRGB(c[0] / 255, c[1] / 255, c[2] / 255); }
const layer3 = {id: 'rocks3d', type: 'custom', renderingMode: '3d',
  onAdd(m, gl) {
    this.camera = new THREE.Camera(); this.scene = new THREE.Scene(); this.renderer = new THREE.WebGLRenderer({canvas: m.getCanvas(), context: gl, antialias: true}); this.renderer.autoClear = false;
    if (!S3.o) mercOrigin();
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.75)); const dl = new THREE.DirectionalLight(0xfff2dd, 1.1); dl.position.set(-0.5, -0.45, 0.74); this.scene.add(dl);
    if (!S3.rocks) {
      const geo = new THREE.IcosahedronGeometry(1, 1), mat = new THREE.MeshLambertMaterial({flatShading: true});
      S3.rocks = new THREE.InstancedMesh(geo, mat, M); S3.rocks.frustumCulled = false; S3.rocks.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      for (let j = 0; j < M; j++) S3.rocks.setColorAt(j, new THREE.Color(0xffffff));
      const K = 60; S3.K = K; S3.hist = new Float32Array(M * K * 3); S3.histN = 0;
      const tg = new THREE.BufferGeometry(); tg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(M * (K - 1) * 2 * 3), 3)); tg.setAttribute('color', new THREE.BufferAttribute(new Float32Array(M * (K - 1) * 2 * 4), 4));
      S3.trail = new THREE.LineSegments(tg, new THREE.LineBasicMaterial({vertexColors: true, transparent: true, depthWrite: false})); S3.trail.frustumCulled = false;
      const NP = 2400, pg = new THREE.BufferGeometry(); pg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(NP * 3), 3)); pg.setAttribute('aA', new THREE.BufferAttribute(new Float32Array(NP), 1)); pg.setAttribute('aS', new THREE.BufferAttribute(new Float32Array(NP), 1));
      S3.dustMat = new THREE.ShaderMaterial({transparent: true, depthWrite: false, uniforms: {uMpp: {value: 1}},
        vertexShader: 'attribute float aA; attribute float aS; varying float vA; uniform float uMpp; void main(){ vA = aA; gl_PointSize = clamp(aS / uMpp, 1.0, 90.0); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
        fragmentShader: 'precision highp float; varying float vA; void main(){ vec2 d = gl_PointCoord - 0.5; float r = length(d); if (r > 0.5) discard; float a = vA * smoothstep(0.5, 0.1, r); gl_FragColor = vec4(0.72, 0.64, 0.52, a * 0.7); }'});
      S3.dust = new THREE.Points(pg, S3.dustMat); S3.dust.frustumCulled = false; S3.NP = NP; S3.dp = new Array(NP).fill(null); S3.dnext = 0;
    }
    this.scene.add(S3.rocks); this.scene.add(S3.trail); this.scene.add(S3.dust);
  },
  render(gl, matrix) {
    const o = S3.o, s = S3.s; const m = new THREE.Matrix4().fromArray(matrix), l = new THREE.Matrix4().makeTranslation(o.x, o.y, 0).scale(new THREE.Vector3(s, -s, s));
    this.camera.projectionMatrix = m.multiply(l); this.renderer.resetState(); this.renderer.render(this.scene, this.camera);
  }};
// ---------- animation state
let tSim = 0, last = null, loopHold = 0;
const posNow = new Float32Array(M * 3), eNow = new Float32Array(M), mov = new Uint8Array(M);
function sampleRock(j, f) {                                              // f = fractional record index
  const k = Math.min(NREC - 1, Math.max(0, Math.floor(f))), k2 = Math.min(NREC - 1, k + 1), w = f - k, i = k * M + j, i2 = k2 * M + j;
  const lon = B[0] + (LON[i] + (LON[i2] - LON[i]) * w), lat = B[1] + (LAT[i] + (LAT[i2] - LAT[i]) * w);
  return [lon, lat, HGT[i] + (HGT[i2] - HGT[i]) * w, SPD[i] + (SPD[i2] - SPD[i]) * w, STA[i]];
}
const tmpM = new THREE.Matrix4(), tmpQ = new THREE.Quaternion(), tmpS = new THREE.Vector3(), tmpP = new THREE.Vector3(), tmpC = new THREE.Color();
function mppNow() { return 78271.517 * Math.cos(DATA.center[1] * Math.PI / 180) / Math.pow(2, map.getZoom()); }
function updateScene(t, advancing) {
  if (!S3.rocks) return;
  const f = t / DT, mpp = mppNow(), K = S3.K; let moving = 0, stopped = 0, vmax = 0, emx = 0;
  const showRocks = ui.mode === 'rocks';
  const hist = S3.hist, trailPos = S3.trail.geometry.attributes.position.array, trailCol = S3.trail.geometry.attributes.color.array;
  if (advancing) { S3.histN = Math.min(K, S3.histN + 1); hist.copyWithin(3 * M, 0, 3 * M * (K - 1)); }
  for (let j = 0; j < M; j++) {
    const [lon, lat, h, v, st] = sampleRock(j, f);
    const released = f * DT >= 0 && (st >= 1 || (f >= 0 && STA[Math.min(NREC - 1, Math.floor(f)) * M + j] >= 1));
    const el = map.queryTerrainElevation([lon, lat], {exaggerated: true}) || 0;
    const rad = DIA[j] / 2, vis = Math.max(rad * ui.size, 6 * mpp);
    const w = llToWorld(lon, lat, el + h + vis * 0.9);
    const E = 0.5 * MASS[j] * v * v / 1000; if (st === 1) { moving++; vmax = Math.max(vmax, v); } else if (st >= 2) stopped++; emx = Math.max(emx, E);
    posNow[3 * j] = w[0]; posNow[3 * j + 1] = w[1]; posNow[3 * j + 2] = w[2];
    const hidden = !showRocks || st === 0;
    tmpP.set(w[0], w[1], w[2]); tmpS.setScalar(hidden ? 0.0001 : vis * (st >= 2 ? 0.8 : 1));
    tmpQ.setFromAxisAngle(new THREE.Vector3(0.3, 0.5, 0.8).normalize(), (j * 1.7 + (st === 1 ? t * v * 0.9 / Math.max(rad, 0.3) * 0.15 : 0)));
    tmpM.compose(tmpP, tmpQ, tmpS); S3.rocks.setMatrixAt(j, tmpM);
    if (st >= 2) tmpC.setRGB(0.22, 0.2, 0.19); else energyColor(E * 1000, tmpC);
    S3.rocks.setColorAt(j, tmpC);
    if (advancing) { hist[3 * j] = w[0]; hist[3 * j + 1] = w[1]; hist[3 * j + 2] = w[2] - vis * 0.8; }
    // dust: an impact inside this record interval and a decent speed
    const kk = Math.floor(f); if (ui.dust && showRocks && IMP[kk * M + j] && v > 2.5 && kk !== S3.lastImp?.[j]) { (S3.lastImp = S3.lastImp || {})[j] = kk; spawnDust(w, Math.min(1, v / 25), t); }
  }
  S3.rocks.instanceMatrix.needsUpdate = true; if (S3.rocks.instanceColor) S3.rocks.instanceColor.needsUpdate = true;
  // trails from the position history (same elevations the rocks were drawn at)
  let n = 0;
  for (let j = 0; j < M; j++) {
    for (let k = 0; k < K - 1; k++) {
      const a = (k * M + j) * 3, b = ((k + 1) * M + j) * 3, ok = ui.trails && showRocks && k + 1 < S3.histN && k < ui.trail;
      const o = n * 6; n++;
      if (!ok) { trailPos[o] = trailPos[o + 3] = 0; trailPos[o + 1] = trailPos[o + 4] = 0; trailPos[o + 2] = trailPos[o + 5] = 0; const c = (n - 1) * 8; for (let q = 0; q < 8; q++) trailCol[c + q] = 0; continue; }
      trailPos[o] = hist[a]; trailPos[o + 1] = hist[a + 1]; trailPos[o + 2] = hist[a + 2]; trailPos[o + 3] = hist[b]; trailPos[o + 4] = hist[b + 1]; trailPos[o + 5] = hist[b + 2];
      const al = Math.pow(1 - k / ui.trail, 1.6) * 0.85, c = (n - 1) * 8; trailCol[c] = 1; trailCol[c + 1] = 0.82; trailCol[c + 2] = 0.45; trailCol[c + 3] = al; trailCol[c + 4] = 1; trailCol[c + 5] = 0.7; trailCol[c + 6] = 0.3; trailCol[c + 7] = al * 0.8;
    }
  }
  S3.trail.geometry.attributes.position.needsUpdate = true; S3.trail.geometry.attributes.color.needsUpdate = true;
  updateDust(t, mpp);
  $('stMoving').textContent = moving + ' / ' + M; $('stStopped').textContent = stopped; $('stSpeed').textContent = vmax.toFixed(0) + ' m/s'; $('stEnergy').textContent = emx >= 1000 ? (emx / 1000).toFixed(1) + ' MJ' : emx.toFixed(0) + ' kJ';
  return {moving, stopped};
}
function spawnDust(w, k, t) { for (let q = 0; q < 6; q++) { const i = S3.dnext; S3.dnext = (S3.dnext + 1) % S3.NP; S3.dp[i] = {x: w[0] + (Math.random() - 0.5) * 3, y: w[1] + (Math.random() - 0.5) * 3, z: w[2] - 0.5, vx: (Math.random() - 0.5) * 2, vy: (Math.random() - 0.5) * 2, vz: 1 + Math.random() * 2.5, t0: t, life: 1.6 + 1.4 * k, size: 2.5 + 7 * k}; } }
function updateDust(t, mpp) {
  const pos = S3.dust.geometry.attributes.position.array, aA = S3.dust.geometry.attributes.aA.array, aS = S3.dust.geometry.attributes.aS.array; S3.dustMat.uniforms.uMpp.value = mpp;
  for (let i = 0; i < S3.NP; i++) { const p = S3.dp[i]; if (!p || !ui.dust) { aA[i] = 0; continue; } const a = t - p.t0; if (a < 0 || a > p.life) { aA[i] = 0; if (a > p.life) S3.dp[i] = null; continue; }
    pos[3 * i] = p.x + p.vx * a; pos[3 * i + 1] = p.y + p.vy * a; pos[3 * i + 2] = p.z + p.vz * a - 0.6 * a * a; aA[i] = (1 - a / p.life) * 0.9; aS[i] = p.size * (1 + a * 1.8); }
  S3.dust.geometry.attributes.position.needsUpdate = true; S3.dust.geometry.attributes.aA.needsUpdate = true; S3.dust.geometry.attributes.aS.needsUpdate = true;
}
// ---------- scene sources
function addScene() {
  if (map.getSource('mapbox-dem')) return;
  map.addSource('mapbox-dem', {type: 'raster-dem', url: 'mapbox://mapbox.mapbox-terrain-dem-v1', tileSize: 512, maxzoom: 14});
  if (ui.terrain) map.setTerrain({source: 'mapbox-dem', exaggeration: ui.exag});
  map.addLayer({id: 'sky', type: 'sky', paint: {'sky-type': 'atmosphere', 'sky-atmosphere-sun-intensity': 8}});
  if (DATA.aoi) { const ring = DATA.aoi.coordinates[0], lons = ring.map(p => p[0]), lats = ring.map(p => p[1]); const pl = Math.max((Math.max(...lons) - Math.min(...lons)) * 6, 0.5), pa = Math.max((Math.max(...lats) - Math.min(...lats)) * 6, 0.5);
    const outer = [[Math.min(...lons) - pl, Math.min(...lats) - pa], [Math.max(...lons) + pl, Math.min(...lats) - pa], [Math.max(...lons) + pl, Math.max(...lats) + pa], [Math.min(...lons) - pl, Math.max(...lats) + pa], [Math.min(...lons) - pl, Math.min(...lats) - pa]];
    map.addSource('aoi-mask', {type: 'geojson', data: {type: 'Feature', geometry: {type: 'Polygon', coordinates: [outer, ring.slice().reverse()]}}});
    map.addLayer({id: 'aoi-mask-layer', type: 'fill', source: 'aoi-mask', paint: {'fill-color': '#04080a', 'fill-opacity': 0.42}}); }
  for (const key of ['reach', 'energy', 'bounce']) { map.addSource('map-' + key, {type: 'image', url: OVER[key], coordinates: COORDS}); map.addLayer({id: 'map-' + key + '-layer', type: 'raster', source: 'map-' + key, paint: {'raster-opacity': ui.opacity, 'raster-fade-duration': 0}, layout: {visibility: 'none'}}); }
  if (DATA.buildings.features.length) { map.addSource('buildings', {type: 'geojson', data: DATA.buildings});
    map.addLayer({id: 'buildings-layer', type: 'fill-extrusion', source: 'buildings', layout: {visibility: ui.buildings ? 'visible' : 'none'}, paint: {'fill-extrusion-color': ['get', 'color'], 'fill-extrusion-height': ['*', ['get', 'height_m'], 2], 'fill-extrusion-base': 0, 'fill-extrusion-opacity': 0.96, 'fill-extrusion-vertical-gradient': true}}); }
  if (DATA.roads.features.length) { map.addSource('roads', {type: 'geojson', data: DATA.roads}); map.addLayer({id: 'roads-layer', type: 'line', source: 'roads', paint: {'line-color': ['get', 'color'], 'line-width': 3.2, 'line-opacity': 0.95}}); }
  if (DATA.barriers.features.length) { map.addSource('barriers', {type: 'geojson', data: DATA.barriers}); map.addLayer({id: 'barriers-layer', type: 'line', source: 'barriers', paint: {'line-color': '#4fc3ff', 'line-width': 4}}); }
  map.addSource('sources', {type: 'geojson', data: DATA.sources}); map.addLayer({id: 'sources-layer', type: 'circle', source: 'sources', paint: {'circle-radius': 2, 'circle-color': '#8a8f94', 'circle-stroke-color': '#fff', 'circle-stroke-width': 0.8}});
  if (HAS3 && !map.getLayer('rocks3d')) map.addLayer(layer3);
  applyLabels(); applyMode();
}
function applyLabels() { const st = map.getStyle(); if (!st) return; for (const l of st.layers) if (l.type === 'symbol') { try { map.setLayoutProperty(l.id, 'visibility', ui.labels ? 'visible' : 'none'); } catch (e) {} } }
function applyMode() {
  for (const key of ['reach', 'energy', 'bounce']) if (map.getLayer('map-' + key + '-layer')) { map.setLayoutProperty('map-' + key + '-layer', 'visibility', ui.mode === key ? 'visible' : 'none'); map.setPaintProperty('map-' + key + '-layer', 'raster-opacity', ui.opacity); }
  if (map.getLayer('map-reach-layer') && ui.mode === 'rocks') { map.setLayoutProperty('map-reach-layer', 'visibility', 'visible'); map.setPaintProperty('map-reach-layer', 'raster-opacity', ui.opacity * 0.32); }
  renderLegend();
}
function renderLegend() {
  const bar = $('legendBar'), lbl = $('legendLbl'), note = $('legendNote');
  if (ui.mode === 'rocks') { bar.style.background = 'linear-gradient(90deg,#faf0a0,#fab43c 30%,#dc3c28 60%,#961e5a 85%,#3c0a64)'; const pe = DATA.stats.peakEnergyKj || 100; lbl.innerHTML = ['0', Math.round(pe * 0.01) + ' kJ', Math.round(pe * 0.1) + ' kJ', Math.round(pe) + ' kJ'].map(s => '<span>' + s + '</span>').join(''); note.textContent = 'Rock colour = its energy now; dark grey = stopped. Faint orange = share of rocks that pass'; return; }
  const m = MAPS[ui.mode], stops = RAMPS[ui.mode]; bar.style.background = 'linear-gradient(90deg,' + stops.map(s => 'rgb(' + s[1].join(',') + ') ' + (s[0] * 100) + '%').join(',') + ')';
  const val = (t) => m.log ? Math.pow(10, t * Math.log10(1 + m.max)) - 1 : (m.sq ? t * t * m.max : t * m.max), fmt = (v) => (m.scale ? m.scale(v) : v) >= 100 ? Math.round(m.scale ? m.scale(v) : v) : (m.scale ? m.scale(v) : v).toFixed(1);
  lbl.innerHTML = [0, 0.33, 0.66, 1].map(t => '<span>' + fmt(val(t)) + (t === 1 ? ' ' + m.unit : '') + '</span>').join(''); note.textContent = m.label;
}
// ---------- panel wiring
const OVER = {reach: mapCanvas('reach'), energy: mapCanvas('energy'), bounce: mapCanvas('bounce')};
ui.panel = true;
document.querySelectorAll('.card').forEach(c => c.addEventListener('click', () => { ui.mode = c.dataset.mode; document.querySelectorAll('.card').forEach(x => x.classList.toggle('active', x === c)); applyMode(); S3.histN = 0; }));
document.querySelectorAll('.tile').forEach(t => t.addEventListener('click', () => { const k = t.dataset.style; if (k === ui.style) return; ui.style = k; document.querySelectorAll('.tile').forEach(x => x.classList.toggle('active', x === t)); map.setStyle(STYLE_URLS[k]); let n = 0; const tryAdd = () => { if (!map.isStyleLoaded() && n++ < 100) { setTimeout(tryAdd, 100); return; } try { addScene(); } catch (e) { console.warn(e); } }; setTimeout(tryAdd, 80); }));
const pill = (id, key, fn) => $(id).addEventListener('click', (e) => { ui[key] = !ui[key]; e.currentTarget.classList.toggle('on', ui[key]); fn && fn(); });
pill('pillBuildings', 'buildings', () => map.getLayer('buildings-layer') && map.setLayoutProperty('buildings-layer', 'visibility', ui.buildings ? 'visible' : 'none'));
pill('pillTerrain', 'terrain', () => ui.terrain ? map.setTerrain({source: 'mapbox-dem', exaggeration: ui.exag}) : map.setTerrain(null)); pill('pillLabels', 'labels', applyLabels); pill('pillTrails', 'trails'); pill('pillDust', 'dust');
const sl = (id, key, fn, scale = 1) => $(id).addEventListener('input', (e) => { ui[key] = parseFloat(e.target.value) / scale; $(id + 'Out').textContent = e.target.value; fn && fn(); });
sl('exagSlider', 'exag', () => ui.terrain && map.setTerrain({source: 'mapbox-dem', exaggeration: ui.exag})); sl('opSlider', 'opacity', applyMode, 100); sl('sizeSlider', 'size'); sl('trailSlider', 'trail');
$('resetBtn').addEventListener('click', resetView); $('collapseBtn').addEventListener('click', () => { const c = $('panel').classList.toggle('collapsed'); document.body.classList.toggle('panel-collapsed', c); });
$('fsBtn').addEventListener('click', () => { const el = document.documentElement; if (!document.fullscreenElement) el.requestFullscreen && el.requestFullscreen(); else document.exitFullscreen && document.exitFullscreen(); });
$('playPauseBtn').addEventListener('click', () => { ui.playing = !ui.playing; $('playPauseBtn').innerHTML = ui.playing ? '&#10074;&#10074;' : '&#9654;'; last = null; });
$('speedSelect').addEventListener('change', () => ui.speed = parseFloat($('speedSelect').value));
const ts = $('timeSlider'); let dragging = false; ts.addEventListener('pointerdown', () => dragging = true); ts.addEventListener('input', () => { tSim = ts.value / 1000 * TMAX; S3.histN = 0; }); ts.addEventListener('pointerup', () => { dragging = false; last = null; });
$('exportPngBtn').addEventListener('click', () => { setTimeout(() => { const a = document.createElement('a'); a.href = map.getCanvas().toDataURL('image/png'); a.download = 'rockfall_3d.png'; a.click(); }, 300); });
$('exportVideoBtn').addEventListener('click', () => {
  const btn = $('exportVideoBtn'); btn.disabled = true; const lab = btn.textContent; btn.textContent = 'Recording...'; tSim = 0; ui.playing = true; last = null; S3.histN = 0;
  setTimeout(() => { const stream = map.getCanvas().captureStream(30), chunks = []; let rec; try { rec = new MediaRecorder(stream, {mimeType: 'video/webm'}); } catch (e) { btn.textContent = lab; btn.disabled = false; return alert('Video recording is not supported: ' + e.message); }
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    rec.onstop = async () => { btn.textContent = 'Encoding...'; const form = new FormData(); form.append('video', new Blob(chunks, {type: 'video/webm'}), 'rock.webm');
      try { const r = await fetch('/export-video', {method: 'POST', body: form}); if (!r.ok) throw new Error('HTTP ' + r.status); const u = URL.createObjectURL(await r.blob()); const a = document.createElement('a'); a.href = u; a.download = 'rockfall_animation.mp4'; a.click(); } catch (e) { alert('Video export failed: ' + e.message); } finally { btn.textContent = lab; btn.disabled = false; } };
    rec.start(); setTimeout(() => rec.stop(), Math.min(60, TMAX / ui.speed) * 1000 + 400); }, 300); });
map.on('click', (e) => {
  const c = Math.floor((e.lngLat.lng - B[0]) / (B[2] - B[0]) * NC), r = Math.floor((B[3] - e.lngLat.lat) / (B[3] - B[1]) * NR); if (c < 0 || r < 0 || c >= NC || r >= NR) return;
  const q = (k) => dec(MAPS[k].q)[r * NC + c] / 255, re = q('reach') * MAPS.reach.max, en = MAPS.energy.log ? Math.pow(10, q('energy') * Math.log10(1 + MAPS.energy.max)) - 1 : 0, bo = q('bounce') * MAPS.bounce.max;
  new mapboxgl.Popup({closeButton: true}).setLngLat(e.lngLat).setHTML('<div style="color:#111;font:12px sans-serif"><b>Rockfall here</b><br>Rocks passing: <b>' + (re * 100).toFixed(1) + '%</b><br>Peak energy: <b>' + Math.round(en) + ' kJ</b><br>Peak bounce height: <b>' + bo.toFixed(1) + ' m</b></div>').addTo(map);
});
// ---------- chart + loop
const chart = $('chart'), cx = chart.getContext('2d'); const SER = (() => { const mv = new Float32Array(NREC), st = new Float32Array(NREC); for (let k = 0; k < NREC; k++) { let a = 0, b = 0; for (let j = 0; j < M; j++) { const s = STA[k * M + j]; if (s === 1) a++; else if (s >= 2) b++; } mv[k] = a; st[k] = b; } return {mv, st}; })();
function drawChart() { const w = chart.width = chart.clientWidth * 2, h = chart.height = 120; cx.clearRect(0, 0, w, h); const sp = (arr, col, fill) => { cx.beginPath(); cx.moveTo(0, h - 12); for (let k = 0; k < NREC; k += 2) cx.lineTo(k / NREC * w, h - 12 - arr[k] / M * (h - 24)); cx.lineTo(w, h - 12); cx.fillStyle = fill; cx.fill(); cx.strokeStyle = col; cx.lineWidth = 2; cx.stroke(); };
  sp(SER.st, '#9aa6ad', 'rgba(154,166,173,0.18)'); sp(SER.mv, '#ffb347', 'rgba(255,179,71,0.25)'); const x = tSim / TMAX * w; cx.strokeStyle = '#fff'; cx.beginPath(); cx.moveTo(x, 0); cx.lineTo(x, h); cx.stroke(); cx.fillStyle = '#9fb8c2'; cx.font = '20px sans-serif'; cx.fillText('rocks moving (orange) / stopped (grey)', 8, 22); }
function fmtT(s) { const m = Math.floor(s / 60); return m + ':' + String(Math.round(s % 60)).padStart(2, '0'); }
function tick(now) {
  requestAnimationFrame(tick);
  try {
    if (!tick._n) tick._n = 0; tick._n++; if (tick._n === 90) document.documentElement.setAttribute('data-ready', '1');
    if (last === null) last = now; const dt = (now - last) / 1000; last = now;
    let adv = false;
    if (ui.playing && !dragging) { tSim += dt * ui.speed; adv = true; if (tSim >= TMAX) { loopHold += dt; tSim = TMAX - 1e-3; if (loopHold > 2.5) { tSim = 0; loopHold = 0; S3.histN = 0; } } }
    if (!dragging) ts.value = Math.round(tSim / TMAX * 1000);
    if (!tick._adv || adv || (now - (tick._lastU || 0) > 250)) { updateScene(tSim, adv); tick._lastU = now; }
    $('timeBig').textContent = fmtT(tSim); $('timeLabel').textContent = fmtT(tSim) + ' / ' + fmtT(TMAX); drawChart(); tick._adv = true; map.triggerRepaint();
  } catch (e) { if (!tick._w) { tick._w = 1; document.documentElement.setAttribute('data-frame-err', String((e && e.stack) || e).slice(0, 500)); } }
}
const _q = new URLSearchParams(location.search);
if (_q.has('t')) { tSim = parseFloat(_q.get('t')) * TMAX; ui.playing = false; }
if (_q.get('panel') === '0') { $('panel').classList.add('collapsed'); document.body.classList.add('panel-collapsed'); ui.panel = false; }
if (_q.get('mode')) setTimeout(() => { const c = document.querySelector('.card[data-mode="' + _q.get('mode') + '"]'); if (c) c.click(); }, 1500);
$('panelSub').textContent = DATA.stats.rocks.toLocaleString() + ' rocks from ' + DATA.stats.sources + ' release cells · ' + M + ' shown';
$('timelineBar').style.display = 'block'; (() => { const st = document.createElement('style'); st.textContent = '.mapboxgl-ctrl-bottom-right,.mapboxgl-ctrl-bottom-left{bottom:var(--tl-h,0px)}'; document.head.appendChild(st); document.documentElement.style.setProperty('--tl-h', ($('timelineBar').offsetHeight + 22) + 'px'); })();
map.on('load', () => { addScene(); resetView(); requestAnimationFrame(tick); });
