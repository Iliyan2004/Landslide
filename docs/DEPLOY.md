# Putting the dashboard on a link that works on any computer

**Two things are served, and they are different.** The dashboard pages (the Gilgit sample in `site/` and every area already built in `datasets/aoi/<id>/`) are static files that any static host can serve. Drawing is part of those pages and works anywhere, but **fetching a new area** needs the Python server (`serve_dashboard.bat`), the 3.3 GB national DEM and the Earth Engine login, so it only works from the computer that holds them. On a static host the Fetch button says so. To let other people fetch areas, they must open the dashboard from the computer running `serve_dashboard.bat` (same network, `http://<its address>:8080/`); the server has no login, so do not expose it to the internet.

To publish a built area on a static host, copy `datasets/aoi/<id>/index.html` into the site folder (for example as `a/<id>/index.html`) together with `config.js` at the root.

The dashboard is a static website: the folder `landslide-platform/site/` holds everything (`index.html`, about 12 MB, and `config.js`). Any static host can serve it. Pick one of the three below; each gives the project its own address. The address names are first come, first served, so the name `gilgit-landslide` may be taken: use another if so.

Do this first:

1. Rebuild so the page is current: `python -I scripts/build_dashboard_page.py`.
2. Check the licences in `docs/licensing_register.csv` (Open Buildings, WorldPop, GLiM, GEM faults and OpenStreetMap-derived data have attribution or share-alike terms).
3. Decide on a Mapbox token. Without one the page uses public tile servers (Esri, OpenTopoMap, OpenStreetMap, CARTO, AWS elevation tiles) whose terms limit heavy use. With one, put `window.MAPBOX_TOKEN = "pk.your_token";` in `site/config.js` and restrict the token to your site's address in your Mapbox account.

## Option A: Netlify (quickest, no command line)

1. Create a free account at netlify.com.
2. Open "Add new site", "Deploy manually", and drag the `site` folder onto the page.
3. In "Site configuration", "Change site name", enter `gilgit-landslide`. The link is `https://gilgit-landslide.netlify.app/`.
4. To update, drag the rebuilt `site` folder onto "Deploys" again.

## Option B: GitHub Pages

1. Create a new repository named `gilgit-landslide` on github.com (public, for the free plan).
2. Upload the contents of `site/` (both files) to the repository root.
3. In "Settings", "Pages", set the source to the `main` branch, root folder.
4. The link is `https://<your-user-name>.github.io/gilgit-landslide/`.

## Option C: Cloudflare Pages

1. Create a free Cloudflare account, open "Workers and Pages", "Create", "Pages", "Upload assets".
2. Name the project `gilgit-landslide` and upload the `site` folder.
3. The link is `https://gilgit-landslide.pages.dev/`.

## Same network only

`serve_dashboard.bat` serves the page on every address of this computer. Another computer on the same network can open `http://<this computer's address>:8080/` while this computer is on and the server is running. Windows may ask to allow Python through the firewall the first time.

## A single file

`docs/gilgit_landslide_dashboard.html` is the same dashboard in one file. It opens by double-click on any computer with internet access (the map libraries and tiles load from the internet) and can be sent by e-mail or shared drive.

Keep the "demonstration, not a hazard forecast" badge on any public copy: the validation record (Technical Reference, Chapter 39) shows the scenario simulation has no skill against the reported landslides.
