"""Load a dashboard page in headless Chrome and report JavaScript errors and key facts.
Usage: python -X utf8 scripts/page_check.py <path to index.html> [--click-site]
The page is copied with an error logger injected; the result is read from the DOM after the page has run."""
import html as H, json, re, subprocess, sys, tempfile
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
src = Path(sys.argv[1]).read_text(encoding="utf-8")
probe = """<script>window.__errs=[];window.addEventListener('error',e=>__errs.push((e.message||'')+' @'+e.lineno+':'+e.colno));window.addEventListener('unhandledrejection',e=>__errs.push('rejection '+(e.reason&&e.reason.message||e.reason)));</script>"""
post = """<script>setTimeout(()=>{const o={errs:window.__errs,aoi:typeof AOI_META!=='undefined'?AOI_META.name:null,events:typeof EVENTS!=='undefined'?EVENTS.length:null,allpts:typeof D!=='undefined'&&D.allpts?D.allpts.length:null,
 cells:typeof NC!=='undefined'?NC:null,area:typeof S!=='undefined'?S.area_km2:null,tabs:document.querySelectorAll('.tab:not([hidden])').length,kv:document.getElementById('aoiKV').innerText,mapNote:document.getElementById('mapNote').innerText,engine:document.getElementById('engine').innerText,mapReady:typeof mapReady!=='undefined'&&mapReady,layers:(typeof map!=='undefined'&&map&&mapReady)?['allinv','aoicur','aoidraw-line','inv','screen'].map(l=>l+':'+!!map.getLayer(l)):null};
 try{map={getSource:()=>({setData(d){window.__drawn=d}}),getCanvas:()=>({style:{}}),project:()=>({x:0,y:0}),fitBounds(){}};mapReady=true;AD.api=true;
 adFinish([[72.35,35.0],[72.45,35.0],[72.45,35.1],[72.35,35.1],[72.35,35.0]]);o.drawn_km2=AD.geom?+ringArea(AD.geom.coordinates[0]).toFixed(1):null;o.status1=el('a-status').textContent;o.fetch_enabled=!el('a-fetch').disabled;
 adStart('poly');o.mode=AD.mode;adClear();o.cleared=!AD.geom;
 aoiAround(72.5,34.5);o.around=AD.geom?+ringArea(AD.geom.coordinates[0]).toFixed(0):null;o.name=el('a-name').value;
 adFinish([[60,24],[75,24],[75,36],[60,36],[60,24]]);o.big=el('a-status').textContent;o.big_fetch=!el('a-fetch').disabled;
 const ex=[]; ['a-rect','a-poly','a-view','a-clear','a-fetch','z-pk','l-all'].forEach(i=>{if(!el(i))ex.push(i)}); o.missing=ex}catch(e){o.drawerr=String(e)}
 const p=document.createElement('pre');p.id='pcres';p.textContent=JSON.stringify(o);document.body.appendChild(p)},8000)</script>"""
page = src.replace("<body>", "<body>" + probe, 1).replace("</body>", post + "</body>")
tmp = Path(tempfile.mkdtemp()) / "page.html"
tmp.write_text(page, encoding="utf-8")
prof = tempfile.mkdtemp()
dom = subprocess.run([CHROME, "--headless=new", f"--user-data-dir={prof}", "--disable-gpu", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--window-size=1400,900", *([] if "--map" in sys.argv else ["--host-resolver-rules=MAP unpkg.com 127.0.0.1, MAP api.mapbox.com 127.0.0.1, MAP fonts.googleapis.com 127.0.0.1"]),
                      "--virtual-time-budget=15000", "--dump-dom", tmp.as_uri()], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240).stdout
m = re.search(r'<pre id="pcres">(.*?)</pre>', dom, re.S)
print(json.dumps(json.loads(H.unescape(m.group(1))), indent=1) if m else "no result; dom length " + str(len(dom)))
