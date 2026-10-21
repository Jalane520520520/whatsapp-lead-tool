"""Find WhatsApp numbers a business publishes on its own website (real browser via crawl4ai).
Usage: python find_wa.py IN.csv OUT.csv [--region GB]
Pages are rendered one at a time (weak CPU). Resume-safe: rows already in OUT.csv are skipped."""
import asyncio, csv, os, re, sys, time, html as htmlmod
from urllib.parse import urlparse, urljoin, unquote
import phonenumbers
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

SKIP_PLATFORMS = ("ubereats.", "deliveroo.", "just-eat.", "justeat.", "doordash.", "grubhub.",
                  "google.", "goo.gl", "facebook.com", "fb.com", "instagram.com")
PAGE_TIMEOUT_MS = 30000
CONTACT_RE = re.compile(r"contact|about|联系|聯絡", re.I)
LINK_PATTERNS = [
    re.compile(r"wa\.me/(?:message/)?\+?(\d{6,15})", re.I),
    re.compile(r"api\.whatsapp\.com/send/?\?[^\"'\s<>]*?phone=(?:%2B|\+)?(\d{6,15})", re.I),
    re.compile(r"web\.whatsapp\.com/send/?\?[^\"'\s<>]*?phone=(?:%2B|\+)?(\d{6,15})", re.I),
    re.compile(r"whatsapp://send/?\?[^\"'\s<>]*?phone=(?:%2B|\+)?(\d{6,15})", re.I),
]
NEW_COLS = ["wa_number_e164", "wa_source_url", "wa_evidence", "site_status"]

def is_platform(url):
    host = urlparse(url).netloc.lower()
    return any(p in host for p in SKIP_PLATFORMS)

def norm_digits(d, region):
    try:
        n = phonenumbers.parse("+" + d, None)
        if phonenumbers.is_valid_number(n):
            return phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        pass
    try:  # national format like 07700900123
        n = phonenumbers.parse(d, region)
        if phonenumbers.is_valid_number(n):
            return phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        pass
    return None

def extract(raw_html, text, region="GB"):
    """returns list of (e164, evidence)"""
    found, seen = [], set()
    blob = unquote(htmlmod.unescape(raw_html or ""))
    for pat in LINK_PATTERNS:
        for m in pat.finditer(blob):
            e = norm_digits(m.group(1), region)
            if e and e not in seen:
                seen.add(e); found.append((e, blob[max(0, m.start()-10):m.end()][:120]))
    text = text or ""
    for m in re.finditer(r"whats\s?app", text, re.I):
        after = text[m.end():m.end()+40]
        before = text[max(0, m.start()-40):m.start()]
        for win in (after, before):  # prefer the number written right after the word
            pms = [p for p in phonenumbers.PhoneNumberMatcher(win, region) if phonenumbers.is_valid_number(p.number)]
            if win is before and pms: pms = pms[-1:]
            if win is after and pms: pms = pms[:1]
            for pm in pms:
                e = phonenumbers.format_number(pm.number, phonenumbers.PhoneNumberFormat.E164)
                if e not in seen:
                    seen.add(e); found.append((e, " ".join(text[max(0, m.start()-40):m.end()+40].split())[:120]))
            if pms: break
    return found

async def render(crawler, url):
    cfg = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=PAGE_TIMEOUT_MS,
                           delay_before_return_html=2.5, wait_until="domcontentloaded",
                           verbose=False)
    r = await crawler.arun(url=url, config=cfg)
    if not r.success:
        raise RuntimeError(r.error_message or "crawl failed")
    md = r.markdown
    text = getattr(md, "raw_markdown", None) or str(md or "")
    return r, r.html or "", text

def contact_link(result, base):
    host = urlparse(base).netloc.replace("www.", "")
    links = (result.links or {}).get("internal", [])
    for l in links:
        href = l.get("href", "")
        if urlparse(href).netloc.replace("www.", "") == host and href.rstrip("/") != base.rstrip("/") \
           and CONTACT_RE.search(urlparse(href).path + " " + (l.get("text") or "")):
            return href
    return None

async def process(crawler, url, region):
    res = {"wa_number_e164": "", "wa_source_url": "", "wa_evidence": "", "site_status": "ok"}
    nums = {}
    try:
        r, h, t = await render(crawler, url)
        for e, ev in extract(h, t, region):
            nums.setdefault(e, (url, ev))
        c = contact_link(r, r.url or url)
        if c:
            try:
                r2, h2, t2 = await render(crawler, c)
                for e, ev in extract(h2, t2, region):
                    nums.setdefault(e, (c, ev))
            except Exception:
                pass
    except Exception as ex:
        res["site_status"] = "error: " + str(ex)[:80].replace("\n", " ")
        return res
    if nums:
        res["wa_number_e164"] = ";".join(nums)
        res["wa_source_url"] = ";".join(v[0] for v in nums.values())
        res["wa_evidence"] = " | ".join(v[1] for v in nums.values())[:120]
    return res

async def main(inp, out, region="GB"):
    rows = list(csv.DictReader(open(inp, encoding="utf-8")))
    done = {}
    if os.path.exists(out):
        for r in csv.DictReader(open(out, encoding="utf-8")):
            done[r["place_id"]] = r
    fields = list(rows[0].keys()) + NEW_COLS
    t0 = time.time(); timings = []
    bc = BrowserConfig(headless=True, verbose=False)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        async with AsyncWebCrawler(config=bc) as crawler:
            for row in rows:
                if row["place_id"] in done:
                    w.writerow({k: done[row["place_id"]].get(k, "") for k in fields}); f.flush(); continue
                url = (row.get("website") or "").strip()
                if not url:
                    res = {"wa_number_e164": "", "wa_source_url": "", "wa_evidence": "", "site_status": "no_site"}
                elif is_platform(url):
                    res = {"wa_number_e164": "", "wa_source_url": "", "wa_evidence": "", "site_status": "skipped_platform"}
                else:
                    s = time.time(); res = await process(crawler, url, region); timings.append(time.time()-s)
                    print(f"{time.time()-s:5.1f}s {url[:50]} -> {res['site_status'][:30]} {res['wa_number_e164']}", flush=True)
                w.writerow({**row, **res}); f.flush()
    print(f"own-site crawled: {len(timings)}, total {time.time()-t0:.0f}s, avg {sum(timings)/max(1,len(timings)):.1f}s/site")

if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2], "GB"))
