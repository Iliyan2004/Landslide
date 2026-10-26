// ---------- area of interest: draw, fetch from the server, open saved areas
const PK_B=[[60.8,23.6],[77.9,37.1]];
const AD={mode:null,pts:[],cur:null,ready:false,api:false,busy:false,geom:null};
const AOI_META=D.aoi||{id:'gilgit',name:'Gilgit (sample area)'};
const emptyAD={type:'FeatureCollection',features:[]};
const geoAll={type:'FeatureCollection',features:(D.allpts||[]).map((p,i)=>({type:'Feature',geometry:{type:'Point',coordinates:[p.lon,p.lat]},properties:{k:/earthquake/.test((p.trig||'').toLowerCase())?'q':/rain|downpour|monsoon|flood/.test((p.trig||'').toLowerCase())?'r':'o',lon:p.lon,lat:p.lat,t:`<b>${p.cat.replace('_',' ')}</b> · ${isoOf(p.date)}<br>trigger: ${p.trig} · size ${p.size.replace('_',' ')}<br>${p.title&&p.title!=='None'?p.title+'<br>':''}<span style="color:#e6b84a">Outside the current area: click to fetch an area around it</span>`}}))};
function ringArea(ring){const pr=ring.map(([lo,la])=>ll2utm(lo,la));let a=0;for(let i=0;i<pr.length-1;i++)a+=pr[i][0]*pr[i+1][1]-pr[i+1][0]*pr[i][1];return Math.abs(a)/2e6}
function ringExtent(ring){const pr=ring.map(([lo,la])=>ll2utm(lo,la)),xs=pr.map(p=>p[0]),ys=pr.map(p=>p[1]);return[(Math.max(...xs)-Math.min(...xs))/1000,(Math.max(...ys)-Math.min(...ys))/1000]}
function adSetGeom(ring){AD.geom=ring?{type:'Polygon',coordinates:[ring]}:null;
 const st=el('a-status'),btn=el('a-fetch');
 if(!ring){btn.disabled=true;st.textContent='';st.hidden=true;return}
 const ar=ringArea(ring),[w,h]=ringExtent(ring);let msg=`Drawn area ${fmt(ar,ar<10?2:0)} km² (${fmt(w,0)} × ${fmt(h,0)} km).`,ok=true;
 if(Math.max(w,h)>500){msg+=' Too large: the limit is 500 km across.';ok=false}
 else if(Math.max(w,h)<10)msg+=' Smaller than 10 km: it will be widened to 10 km around its centre.';
 else if(Math.max(w,h)>110)msg+=` The terrain will be held at ${fmt(30*Math.ceil(Math.max(w,h)*1000/30/3600),0)} m cells.`;
 st.hidden=false;st.textContent=msg;btn.disabled=!(ok&&AD.api&&!AD.busy)}
function adRefresh(){if(!mapReady)return;const f=[];let ring=null;
 if(AD.mode==='rect'&&AD.pts.length===1&&AD.cur){const a=AD.pts[0],b=AD.cur;ring=[[a[0],a[1]],[b[0],a[1]],[b[0],b[1]],[a[0],b[1]],[a[0],a[1]]]}
 else if(AD.mode==='poly'&&AD.pts.length){const c=AD.cur?[...AD.pts,AD.cur]:AD.pts;ring=[...c,c[0]]}
 else if(AD.geom)ring=AD.geom.coordinates[0];
 if(ring&&ring.length>=2){f.push({type:'Feature',geometry:{type:ring.length>=4?'Polygon':'LineString',coordinates:ring.length>=4?[ring]:ring},properties:{}})}
 AD.pts.forEach(p=>f.push({type:'Feature',geometry:{type:'Point',coordinates:p},properties:{}}));
 const s=map.getSource('aoidraw');if(s)s.setData({type:'FeatureCollection',features:f})}
function adStart(mode){AD.mode=mode;AD.pts=[];AD.cur=null;AD.geom=null;adSetGeom(null);if(map)map.getCanvas().style.cursor='crosshair';
 el('a-rect').setAttribute('aria-pressed',mode==='rect');el('a-poly').setAttribute('aria-pressed',mode==='poly');
 const st=el('a-status');st.hidden=false;st.textContent=mode==='rect'?'Click two opposite corners.':'Click the corners of the area; double-click or click the first point to finish.';adRefresh()}
function adFinish(ring){AD.mode=null;AD.pts=[];AD.cur=null;if(map)map.getCanvas().style.cursor='';el('a-rect').setAttribute('aria-pressed',false);el('a-poly').setAttribute('aria-pressed',false);adSetGeom(ring);adRefresh()}
function adClear(){AD.mode=null;AD.pts=[];AD.cur=null;AD.geom=null;if(map)map.getCanvas().style.cursor='';el('a-rect').setAttribute('aria-pressed',false);el('a-poly').setAttribute('aria-pressed',false);adSetGeom(null);adRefresh()}
function aoiLayers(){
 map.addSource('allinv',{type:'geojson',data:geoAll});
 map.addLayer({id:'allinv',type:'circle',source:'allinv',layout:{visibility:visOn('l-all')?'visible':'none'},paint:{'circle-radius':['interpolate',['linear'],['zoom'],4,2.5,10,5],'circle-color':['match',['get','k'],'q','#8b7cf6','r','#2fd0d6','#c0ccd4'],'circle-opacity':.75,'circle-stroke-color':'#04141a','circle-stroke-width':1}},map.getLayer('inv')?'inv':undefined);
 map.addSource('aoicur',{type:'geojson',data:{type:'Feature',geometry:AOI_META.polygon||null,properties:{}}});
 map.addLayer({id:'aoicur',type:'line',source:'aoicur',paint:{'line-color':'#e6b84a','line-width':2.2,'line-dasharray':[2,2]}});
 map.addSource('aoidraw',{type:'geojson',data:emptyAD});
 map.addLayer({id:'aoidraw-fill',type:'fill',source:'aoidraw',filter:['==',['geometry-type'],'Polygon'],paint:{'fill-color':'#2fd0d6','fill-opacity':.16}});
 map.addLayer({id:'aoidraw-line',type:'line',source:'aoidraw',paint:{'line-color':'#2fd0d6','line-width':2.4}});
 map.addLayer({id:'aoidraw-pt',type:'circle',source:'aoidraw',filter:['==',['geometry-type'],'Point'],paint:{'circle-radius':5,'circle-color':'#fff','circle-stroke-color':'#2fd0d6','circle-stroke-width':2}});
 adRefresh()}
function aoiHandlers(){
 map.on('click',e=>{if(!AD.mode)return;const p=[+e.lngLat.lng.toFixed(5),+e.lngLat.lat.toFixed(5)];
  if(AD.mode==='rect'){if(AD.pts.length===0){AD.pts=[p];AD.cur=p;adRefresh()}else{const a=AD.pts[0];if(a[0]===p[0]||a[1]===p[1])return;adFinish([[a[0],a[1]],[p[0],a[1]],[p[0],p[1]],[a[0],p[1]],[a[0],a[1]]])}}
  else{if(AD.pts.length>=3){const f=map.project(AD.pts[0]),c=e.point;if(Math.hypot(f.x-c.x,f.y-c.y)<10){adFinish([...AD.pts,AD.pts[0]]);return}}AD.pts.push(p);adRefresh()}});
 map.on('mousemove',e=>{if(!AD.mode||!AD.pts.length)return;AD.cur=[e.lngLat.lng,e.lngLat.lat];adRefresh()});
 map.on('dblclick',e=>{if(AD.mode==='poly'){e.preventDefault();if(AD.pts.length>=3)adFinish([...AD.pts,AD.pts[0]])}});
 map.on('mouseenter','allinv',()=>{if(!AD.mode)map.getCanvas().style.cursor='pointer'});
 map.on('mouseleave','allinv',()=>{if(!AD.mode)map.getCanvas().style.cursor='';popup.remove()});
 map.on('mousemove','allinv',e=>{if(AD.mode)return;popup.setLngLat(e.lngLat).setHTML(e.features[0].properties.t).addTo(map)});
 map.on('click','allinv',e=>{if(AD.mode)return;const q=e.features[0].properties;popup.remove();aoiAround(q.lon,q.lat)})}
function aoiAround(lon,lat,km){km=km||25;const[E,N]=ll2utm(lon,lat),h=km*500,ring=[utm2ll(E-h,N-h),utm2ll(E+h,N-h),utm2ll(E+h,N+h),utm2ll(E-h,N+h),utm2ll(E-h,N-h)].map(p=>[+p[0].toFixed(5),+p[1].toFixed(5)]);
 adFinish(ring);el('a-name').value=el('a-name').value||`Area around ${lat.toFixed(2)}N ${lon.toFixed(2)}E`;
 el('t-terrain').click();const b=ring.map(p=>p),xs=b.map(p=>p[0]),ys=b.map(p=>p[1]);map.fitBounds([[Math.min(...xs),Math.min(...ys)],[Math.max(...xs),Math.max(...ys)]],{padding:80,duration:1200,pitch:0,bearing:0})}
async function aoiFetch(){if(!AD.geom||AD.busy)return;AD.busy=true;const st=el('a-status'),btn=el('a-fetch');btn.disabled=true;
 const body={geometry:AD.geom,name:(el('a-name').value||'').trim()||'My area',deep:el('a-deep').checked};
 try{const r=await fetch('/api/aoi',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const j=await r.json();
  if(!r.ok)throw new Error(j.error||('HTTP '+r.status));
  if(j.state==='done'){location.href='/a/'+j.id+'/';return}
  st.hidden=false;st.textContent='Started …';
  const poll=async()=>{try{const q=await(await fetch('/api/job/'+j.job)).json();st.textContent=(q.messages||[]).slice(-1)[0]||'Working …';st.textContent+=`  (${q.elapsed||0} s)`;
    if(q.state==='done'){location.href='/a/'+q.id+'/';return}
    if(q.state==='failed'){st.textContent='Failed: '+q.error;AD.busy=false;adSetGeom(AD.geom?AD.geom.coordinates[0]:null);return}
    setTimeout(poll,2000)}catch(e){st.textContent='Lost contact with the server: '+e.message;AD.busy=false}};
  poll()}catch(e){st.hidden=false;st.textContent='Could not start: '+e.message;AD.busy=false;adSetGeom(AD.geom.coordinates[0])}}
async function aoiList(){try{const j=await(await fetch('/api/aois')).json();
 el('a-list').innerHTML=`<div class="evrow"><div><b>Gilgit (sample area)</b><br><small style="color:var(--muted)">built-in, with the full validation record</small></div><a class="chip" href="/" style="text-decoration:none">Open</a></div>`+
  j.aois.map(a=>`<div class="evrow"><div><b>${a.name.replace(/</g,'&lt;')}</b>${a.id===AOI_META.id?' <small style="color:var(--cyan)">current</small>':''}<br><small style="color:var(--muted)">${fmt(a.area_km2,0)} km² · ${a.events} reports · ${a.deep?'with satellite layers':'basic'} · ${a.built}</small></div><a class="chip" href="/a/${a.id}/" style="text-decoration:none">Open</a></div>`).join('')}catch(e){}}
async function aoiInit(){
 const kv=[['Current area',AOI_META.name],['Valid area',fmt(S.area_km2)+' km²'],['Cell size',fmt(S.res,0)+' m terrain, '+fmt(D.cell_m,0)+' m web grid'],['Reports inside',EVENTS.length+' of '+(D.allpts?D.allpts.length:D.pts.length)]];
 if(AOI_META.built)kv.push(['Built',AOI_META.built+(AOI_META.seconds?' ('+AOI_META.seconds+' s)':'')]);
 el('aoiKV').innerHTML=kv.map(([k,v])=>`<span>${k}</span><b>${String(v).replace(/</g,'&lt;')}</b>`).join('');
 el('aoiName').textContent=AOI_META.name;
 try{const r=await fetch('/api/health',{cache:'no-store'});AD.api=r.ok}catch(e){AD.api=false}
 el('a-note').textContent=AD.api?'Draw a rectangle or polygon anywhere in Pakistan, or click a grey report point on the map, then fetch the details for that area. Cells outside your polygon are left out. Areas up to 500 km across are accepted; fetching takes one to several minutes.':'Drawing works, but fetching details needs the Python server: run serve_dashboard.bat on the computer that holds the data, then open the page from it.';
 if(AD.api)aoiList()}
el('a-rect').addEventListener('click',()=>adStart(AD.mode==='rect'?null:'rect'));
el('a-poly').addEventListener('click',()=>adStart(AD.mode==='poly'?null:'poly'));
el('a-clear').addEventListener('click',adClear);
el('a-fetch').addEventListener('click',aoiFetch);
el('a-view').addEventListener('click',()=>{if(!map)return;const b=map.getBounds(),w=b.getWest(),e_=b.getEast(),s_=b.getSouth(),n=b.getNorth();const ring=[[w,s_],[e_,s_],[e_,n],[w,n],[w,s_]].map(p=>[+p[0].toFixed(5),+p[1].toFixed(5)]);adFinish(ring)});
el('z-pk').addEventListener('click',()=>{if(map)map.fitBounds(PK_B,{padding:20,pitch:0,bearing:0,duration:1400,essential:true})});
