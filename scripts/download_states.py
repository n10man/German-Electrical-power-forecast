"""Download the 16 German state boundaries (BKG VG250, land areas only, gf=4) as GeoJSON from the official BKG WFS.
Licence: Datenlizenz Deutschland - Namensnennung 2.0 (dl-de/by-2-0), credit line: (c) BKG (year of last data retrieval) dl-de/by-2-0, Datenquellen: https://sg.geodatenzentrum.de/web_public/gdz/datenquellen/datenquellen_vg_nuts.pdf"""
from pathlib import Path
import requests
URL = ("https://sgx.geodatenzentrum.de/wfs_vg250?service=WFS&version=2.0.0&request=GetFeature&typeNames=vg250:vg250_lan"
       "&outputFormat=application/json&srsName=EPSG:4326&cql_filter=gf%3D4")
out = Path("data/raw/vg250_lan.geojson"); out.parent.mkdir(parents=True, exist_ok=True)
r = requests.get(URL, timeout=180); r.raise_for_status(); out.write_bytes(r.content); print(out, len(r.content), "bytes")
