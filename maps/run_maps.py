#!/usr/bin/env python3
"""Cover an area on Google Maps with a grid (gosom/google-maps-scraper) and
output deduplicated businesses with E.164 phones.
Usage: run_maps.py --keyword "hot pot base supplier" --country GB --out out.csv
       run_maps.py --keyword X --bbox 51.48,-0.20,51.54,-0.05 --cell-km 2 --country GB --out out.csv
"""
import argparse, csv, json, math, os, platform, subprocess, sys, time
import phonenumbers
from phonenumbers import PhoneNumberType as T

HERE = os.path.dirname(os.path.abspath(__file__))
COLS = ["name", "phone_e164", "phone_type", "website", "address", "category",
        "latitude", "longitude", "maps_link", "place_id"]


def binary():
    if os.environ.get("WAT_GOSOM"):
        return os.environ["WAT_GOSOM"]
    if platform.system() == "Windows":
        return os.path.join(HERE, "bin", "google_maps_scraper-1.18.1-windows-amd64.exe")
    if platform.system() == "Darwin":
        for n in ("gosom", "google_maps_scraper-1.18.1-darwin-amd64"):
            p = os.path.join(HERE, "bin", n)
            if os.path.exists(p):
                return p
    return os.path.join(HERE, "bin", "google_maps_scraper-1.18.1-linux-amd64")


def default_zoom(cell):
    # A ~1000px-wide Maps viewport spans ~3.7km at z15 (lat 51), ~1.9km at z16,
    # halving per level. Pick the zoom whose viewport is about the cell size.
    for lim, z in ((1, 17), (2, 16), (5, 15), (10, 14), (25, 13)):
        if cell <= lim:
            return z
    return 12


def grid_cells(b, cell):
    la0, lo0, la1, lo1 = b
    dlat = cell / 111.0
    mid = math.cos(math.radians((la0 + la1) / 2))
    dlon = cell / (111.0 * max(mid, 0.05))
    return max(1, math.ceil((la1 - la0) / dlat)) * max(1, math.ceil((lo1 - lo0) / dlon))


def norm_phone(raw, region):
    if not raw:
        return "", "unknown"
    try:
        n = phonenumbers.parse(raw, region)
        if not phonenumbers.is_valid_number(n):
            return "", "unknown"
        t = phonenumbers.number_type(n)
        tt = {T.MOBILE: "mobile", T.FIXED_LINE: "fixed_line",
              T.FIXED_LINE_OR_MOBILE: "fixed_line_or_mobile"}.get(t, "unknown")
        return phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164), tt
    except Exception:
        return "", "unknown"


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--keyword", required=True)
    a.add_argument("--country", help="ISO2, bbox from countries.json and phone region")
    a.add_argument("--bbox", help="minLat,minLon,maxLat,maxLon (overrides country box)")
    a.add_argument("--cell-km", type=float, default=6)
    a.add_argument("--zoom", type=int)
    a.add_argument("--depth", type=int, default=2)  # gosom issue #338: depth>=3 crashes since 2026-10-01
    a.add_argument("--concurrency", type=int, default=1)
    a.add_argument("--inactivity", default="3m")
    a.add_argument("--no-clip", action="store_true", help="keep rows outside the bbox")
    a.add_argument("--out", default="out.csv")
    a = a.parse_args()
    region = (a.country or "").upper() or None
    if a.bbox:
        bbox = [float(x) for x in a.bbox.split(",")]
    elif region:
        c = json.load(open(os.path.join(HERE, "countries.json")))[region]
        bbox = [c["min_lat"], c["min_lon"], c["max_lat"], c["max_lon"]]
    else:
        sys.exit("need --country or --bbox")
    if not region:
        print("warning: no --country, phones without +CC will be dropped", file=sys.stderr)
    zoom = a.zoom or default_zoom(a.cell_km)
    cells = grid_cells(bbox, a.cell_km)
    tmp = os.path.splitext(os.path.abspath(a.out))[0]
    qf, raw = tmp + ".queries.txt", tmp + ".raw.csv"
    open(qf, "w").write(a.keyword + "\n")
    if os.path.exists(raw):
        os.remove(raw)
    cmd = [binary(), "-input", qf, "-results", raw, "-grid-bbox", ",".join(map(str, bbox)),
           "-grid-cell", str(a.cell_km), "-zoom", str(zoom), "-depth", str(a.depth),
           "-c", str(a.concurrency), "-exit-on-inactivity", a.inactivity]
    print(f"cells~{cells} zoom={zoom} bbox={bbox}\n{' '.join(cmd)}", flush=True)
    t0 = time.time()
    subprocess.run(cmd, check=False)
    wall = time.time() - t0
    rows = list(csv.DictReader(open(raw, encoding="utf-8"))) if os.path.exists(raw) else []
    seen, out, clipped = set(), [], 0
    for r in rows:
        pid = r.get("place_id") or r.get("data_id") or r.get("cid") or r.get("link")
        if pid in seen:
            continue
        seen.add(pid)
        try:
            lat, lon = float(r["latitude"]), float(r["longitude"])
        except (KeyError, ValueError):
            lat = lon = None
        if not a.no_clip and lat is not None and not (bbox[0] <= lat <= bbox[2] and bbox[1] <= lon <= bbox[3]):
            clipped += 1
            continue
        ph, pt = norm_phone(r.get("phone", ""), region)
        out.append({"name": r.get("title", ""), "phone_e164": ph, "phone_type": pt,
                    "website": r.get("website", ""), "address": r.get("address", ""),
                    "category": r.get("category", ""), "latitude": r.get("latitude", ""),
                    "longitude": r.get("longitude", ""), "maps_link": r.get("link", ""),
                    "place_id": r.get("place_id", "") or r.get("data_id", "")})
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLS)
        w.writeheader()
        w.writerows(out)
    n = len(out) or 1
    pct = lambda k: round(100 * sum(1 for o in out if k(o)) / n)
    print(json.dumps({"cells": cells, "raw_rows": len(rows), "unique": len(out), "clipped_outside_bbox": clipped,
                      "pct_phone": pct(lambda o: o["phone_e164"]), "pct_website": pct(lambda o: o["website"]),
                      "pct_mobile": pct(lambda o: o["phone_type"] == "mobile"),
                      "wall_s": round(wall)}))


if __name__ == "__main__":
    main()
