#!/usr/bin/env python3
"""Small Google Maps collector using the Python Playwright already in the app.

It intentionally returns the same raw field names consumed by run_maps.py so
the rest of the pipeline (phone normalization, bbox clipping and deduplication)
does not know which browser engine collected the places.
"""
import asyncio
import os
import re
from urllib.parse import quote_plus, unquote

from playwright.async_api import async_playwright


def _last_line(value):
    lines = [line.strip() for line in (value or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


async def _text(locator):
    try:
        if await locator.count():
            return _last_line(await locator.first.inner_text(timeout=3000))
    except Exception:
        pass
    return ""


async def _href(locator):
    try:
        if await locator.count():
            return (await locator.first.get_attribute("href", timeout=3000)) or ""
    except Exception:
        pass
    return ""


def _ids_and_coords(url):
    place = re.search(r"!1s([^!]+)", url)
    lat = re.search(r"!3d(-?\d+(?:\.\d+)?)", url)
    lon = re.search(r"!4d(-?\d+(?:\.\d+)?)", url)
    return (
        unquote(place.group(1)) if place else url,
        lat.group(1) if lat else "",
        lon.group(1) if lon else "",
    )


async def _accept_consent(page):
    for label in ("Accept all", "I agree"):
        try:
            button = page.get_by_role("button", name=label)
            if await button.count():
                await button.first.click(timeout=2000)
                await page.wait_for_timeout(800)
                return
        except Exception:
            pass


async def _result_links(page, depth):
    await _accept_consent(page)
    try:
        await page.locator('div[role="feed"]').wait_for(timeout=12000)
    except Exception:
        if "/maps/place/" in page.url:
            return [page.url]
        return []
    feed = page.locator('div[role="feed"]').first
    rounds_without_change = 0
    previous = 0
    for _ in range(max(1, depth)):
        await feed.evaluate("el => el.scrollTo(0, el.scrollHeight)")
        await page.wait_for_timeout(1200)
        count = await feed.locator('a[href*="/maps/place/"]').count()
        rounds_without_change = rounds_without_change + 1 if count == previous else 0
        previous = count
        if rounds_without_change >= 1:
            break
    return await feed.locator('a[href*="/maps/place/"]').evaluate_all(
        "els => [...new Set(els.map(e => e.href))]"
    )


async def _place(browser, url):
    page = await browser.new_page(locale="en-US", viewport={"width": 1280, "height": 900})
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await _accept_consent(page)
        await page.locator("h1").first.wait_for(timeout=10000)
        await page.wait_for_timeout(500)
        final_url = page.url
        pid, lat, lon = _ids_and_coords(final_url)
        phone_id = ""
        phone_button = page.locator('[data-item-id^="phone:tel:"]')
        if await phone_button.count():
            phone_id = (await phone_button.first.get_attribute("data-item-id")) or ""
        phone = phone_id.removeprefix("phone:tel:") or await _text(phone_button)
        return {
            "title": await _text(page.locator("h1")),
            "phone": phone,
            "website": await _href(page.locator('[data-item-id="authority"]')),
            "address": await _text(page.locator('[data-item-id="address"]')),
            "category": await _text(page.locator('button[jsaction$=".category"]')),
            "latitude": lat,
            "longitude": lon,
            "link": final_url,
            "place_id": pid,
        }
    except Exception as exc:
        print(f"playwright detail failed: {url[:100]}: {type(exc).__name__}: {exc}", flush=True)
        return None
    finally:
        await page.close()


async def collect(keyword, bbox, zoom, depth=2):
    lat = (bbox[0] + bbox[2]) / 2
    lon = (bbox[1] + bbox[3]) / 2
    url = f"https://www.google.com/maps/search/{quote_plus(keyword)}/@{lat},{lon},{zoom}z?hl=en"
    async with async_playwright() as pw:
        launch = {"headless": True}
        if os.environ.get("WAT_BROWSER_CHANNEL"):
            launch["channel"] = os.environ["WAT_BROWSER_CHANNEL"]
        browser = await pw.chromium.launch(**launch)
        search = await browser.new_page(locale="en-US", viewport={"width": 1280, "height": 900})
        try:
            await search.goto(url, wait_until="domcontentloaded", timeout=45000)
            links = await _result_links(search, depth)
            print(f"playwright maps: {len(links)} result links", flush=True)
        finally:
            await search.close()
        rows = []
        for i, link in enumerate(links, 1):
            row = await _place(browser, link)
            if row and row["title"]:
                rows.append(row)
            print(f"playwright maps: detail {i}/{len(links)}", flush=True)
        await browser.close()
        return rows


def collect_sync(keyword, bbox, zoom, depth=2):
    return asyncio.run(collect(keyword, bbox, zoom, depth))
