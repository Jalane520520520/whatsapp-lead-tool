#!/usr/bin/env python3
"""Build cities.json from the GeoNames cities15000 dump (free, CC-BY 4.0).
Source: https://download.geonames.org/export/dump/cities15000.zip  (downloaded 2026-10-17)
Usage: build_cities.py path/to/cities15000.txt   -> writes app/cities.json
Only countries listed in maps/countries.json are kept. Columns used: asciiname, lat, lon, country, population."""
import csv, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
countries = [k for k in json.load(open(os.path.join(HERE, "..", "maps", "countries.json"), encoding="utf-8")) if not k.startswith("_")]
out = {"_source": "GeoNames cities15000 dump, https://download.geonames.org/export/dump/cities15000.zip, CC-BY 4.0 (geonames.org), downloaded 2026-10-17"}
for c in countries: out[c] = []
for r in csv.reader(open(sys.argv[1], encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE):
    if r[8] in out:
        out[r[8]].append({"name": r[2], "lat": round(float(r[4]), 5), "lon": round(float(r[5]), 5), "population": int(r[14])})
for c in countries: out[c].sort(key=lambda x: -x["population"])
json.dump(out, open(os.path.join(HERE, "cities.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print({c: len(out[c]) for c in countries})
