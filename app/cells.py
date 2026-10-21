"""City list -> ordered 1 km cells, plus the progress ledger (progress.json) helpers.
Our defaults (not from any source): city square side by population, 1 km cells (best yield measured, maps/NOTES.md)."""
import hashlib, json, math, os, re, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
import paths
DATA = paths.DATA
TABLES = paths.TABLES   # what the client sees: only Excel files, readable names
CN = {"GB": "英国", "US": "美国", "AU": "澳大利亚", "DE": "德国", "FR": "法国", "MY": "马来西亚", "SG": "新加坡",
      "AE": "阿联酋", "SA": "沙特阿拉伯", "IN": "印度", "BR": "巴西", "CA": "加拿大", "NZ": "新西兰", "IT": "意大利",
      "ES": "西班牙", "NL": "荷兰", "TH": "泰国", "VN": "越南", "ID": "印度尼西亚", "PH": "菲律宾", "JP": "日本", "KR": "韩国"}


def excel_path(country, keywords):
    kws = sorted({k.strip() for k in keywords if k.strip()}, key=str.lower)
    name = re.sub(r'[\\/:*?"<>|]+', " ", f"{CN.get(country.upper(), country.upper())} - {'; '.join(kws)}").strip()[:120]
    return os.path.join(TABLES, name + ".xlsx")
# --- our default city sizes: (min population, square side in km), checked top to bottom ---
CITY_SIDE_KM = ((1_000_000, 20), (300_000, 12), (100_000, 8), (0, 5))
CELL_KM = 1


def side_km(pop):
    for lim, s in CITY_SIDE_KM:
        if pop >= lim:
            return s


def load_cities(country):
    return json.load(open(os.path.join(HERE, "cities.json"), encoding="utf-8")).get(country.upper(), [])


def city_cells(c):
    """Cells of one city, ordered from the centre outward. Cell = dict(id, bbox[minLat,minLon,maxLat,maxLon])."""
    s = side_km(c["population"])
    dlat = 1 / 111.0
    dlon = 1 / (111.0 * max(math.cos(math.radians(c["lat"])), 0.05))
    out = []
    for iy in range(s):
        for ix in range(s):
            y0, x0 = iy - s / 2, ix - s / 2           # km offsets of the cell's south-west corner
            d = math.hypot(x0 + .5, y0 + .5)
            out.append((d, iy, ix, [round(c["lat"] + y0 * dlat, 5), round(c["lon"] + x0 * dlon, 5),
                                    round(c["lat"] + (y0 + 1) * dlat, 5), round(c["lon"] + (x0 + 1) * dlon, 5)]))
    out.sort(key=lambda t: t[:3])
    return [{"city": c["name"], "n": i + 1, "id": f"{c['name']}#{i + 1}", "bbox": b} for i, (_, _, _, b) in enumerate(out)]


def build_cells(country):
    """All cities, biggest first. A smaller city whose centre lies inside an already-listed bigger city's square is skipped
    (GeoNames lists London boroughs etc. separately; they would only repeat cells)."""
    squares, cells, names = [], [], set()
    for c in sorted(load_cities(country), key=lambda x: -x["population"]):
        if any(a[0] <= c["lat"] <= a[2] and a[1] <= c["lon"] <= a[3] for a in squares):
            continue
        c = dict(c)
        if c["name"] in names:      # two different cities with one name (e.g. Newport)
            c["name"] = f"{c['name']} ({c['lat']:.2f},{c['lon']:.2f})"
        names.add(c["name"])
        cc = city_cells(c)
        sq = [min(x["bbox"][0] for x in cc), min(x["bbox"][1] for x in cc), max(x["bbox"][2] for x in cc), max(x["bbox"][3] for x in cc)]
        squares.append(sq)
        cells += cc
    return cells


def slug_for(country, keywords):
    kws = sorted({k.strip().lower() for k in keywords if k.strip()})
    h = hashlib.sha1("|".join(kws).encode()).hexdigest()[:6]
    base = re.sub(r"[^a-z0-9]+", "_", "_".join(kws)).strip("_")[:30] or "kw"
    return f"{country.upper()}_{base}_{h}"


def data_dir(country, keywords):
    return os.path.join(DATA, slug_for(country, keywords))


def load_progress(country, keywords):
    """progress.json: {country, keywords, cells:[{city,n,id,bbox,status,rows,time}]}. Created on first use."""
    d = data_dir(country, keywords)
    p = os.path.join(d, "progress.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return {"country": country.upper(), "keywords": sorted({k.strip() for k in keywords if k.strip()}),
            "cells": [dict(c, status="") for c in build_cells(country)]}


def save_progress(country, keywords, prog):
    d = data_dir(country, keywords)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(prog, f, ensure_ascii=False, separators=(",", ":"))
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, os.path.join(d, "progress.json"))   # atomic: a kill never leaves a half file


def summary(prog):
    cells = prog["cells"]
    done = sum(1 for c in cells if c.get("status") == "done")
    by = {}
    for c in cells:
        t = by.setdefault(c["city"], [0, 0]); t[1] += 1; t[0] += c.get("status") == "done"
    nxt = next((c for c in cells if c.get("status") != "done"), None)
    return {"done": done, "total": len(cells), "cities_done": [k for k, (a, b) in by.items() if a == b],
            "next_city": nxt["city"] if nxt else "", "next_n": nxt["n"] if nxt else 0}
