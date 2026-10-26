#!/usr/bin/env python3
"""Screenshot a LANDLAB 3D scene through the Chromium DevTools protocol, waiting until the scene is really ready (data-ready) before each capture.
Usage: shot.py URL OUT_PREFIX [--times 0.1,0.4] [--eval JS] [--size 1500x900] [--wait 12]
For each time t in 0..1 it sets the playback position and captures OUT_PREFIX_<t>.png. Chromium (snap) can only write under $HOME."""
import argparse, base64, json, os, subprocess, sys, time, urllib.request
import websocket

ap = argparse.ArgumentParser()
ap.add_argument("url"); ap.add_argument("out")
ap.add_argument("--times", default=""); ap.add_argument("--eval", default=""); ap.add_argument("--size", default="1500x900"); ap.add_argument("--wait", type=float, default=90)
ap.add_argument("--settle", type=float, default=2.0); ap.add_argument("--port", type=int, default=9333)
a = ap.parse_args()
w, h = a.size.split("x")
prof = os.path.expanduser("~/ls_shots/prof"); os.makedirs(prof, exist_ok=True)
proc = subprocess.Popen(["chromium-browser", "--headless=new", "--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", f"--window-size={w},{h}",
                         f"--remote-debugging-port={a.port}", f"--user-data-dir={prof}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try:
            tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{a.port}/json")); break
        except Exception:
            time.sleep(0.5)
    ws = websocket.create_connection([t for t in tabs if t["type"] == "page"][0]["webSocketDebuggerUrl"], timeout=60, suppress_origin=True)
    _id = [0]
    def call(method, **params):
        _id[0] += 1; ws.send(json.dumps({"id": _id[0], "method": method, "params": params}))
        while True:
            m = json.loads(ws.recv())
            if m.get("id") == _id[0]:
                return m.get("result", {})
    def ev(js):
        r = call("Runtime.evaluate", expression=js, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")
    call("Page.enable"); call("Runtime.enable")
    call("Emulation.setDeviceMetricsOverride", width=int(w), height=int(h), deviceScaleFactor=1, mobile=False)
    call("Page.navigate", url=a.url)
    t0 = time.time()
    while time.time() - t0 < a.wait and ev("document.documentElement.getAttribute('data-ready')") != "1":
        time.sleep(0.5)
    ready = ev("document.documentElement.getAttribute('data-ready')") == "1"
    errs = ev("['data-err','data-frame-err','data-shader-err','data-map-err'].map(k=>k+'='+document.documentElement.getAttribute(k)).filter(x=>!x.endsWith('=null')).join(' | ')")
    print("ready:", ready, "| errors:", errs or "none", flush=True)
    if a.eval:
        print("eval:", ev(a.eval)); time.sleep(a.settle)
    times = [float(x) for x in a.times.split(",") if x] or [None]
    for t in times:
        if t is not None:
            ev(f"(typeof tSim!=='undefined')?(tSim={t}*TMAX,ui.playing=false,S3.histN=0):(elapsedSeconds={t}*LOOP_SECONDS,playing=false)")
        time.sleep(a.settle)
        shot = call("Page.captureScreenshot", format="png")
        fn = f"{a.out}_{t:g}.png" if t is not None else f"{a.out}.png"
        open(fn, "wb").write(base64.b64decode(shot["data"])); print("saved", fn, flush=True)
finally:
    try:
        proc.terminate()
    except Exception:
        pass
    subprocess.run(['pkill', '-f', 'remote-debugging-port=%d' % a.port], capture_output=True)
