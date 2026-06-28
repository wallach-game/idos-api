from fastapi import APIRouter, Request
import app as core

router = APIRouter(prefix="/api")

IDOS_URL = "https://idos.cz/vlakyautobusymhdvse/spojeni/"


async def fill_station(page, field_id, ac_id, name):
    field = page.locator(f"#{field_id}")
    await field.click()
    await field.press_sequentially(name, delay=80)
    await page.wait_for_selector(f"#{ac_id} li", timeout=15000)
    await page.click(f"#{ac_id} li:first-child")
    await page.wait_for_selector(f"#{ac_id} li", state="hidden", timeout=5000)


async def collect_boxes(page):
    results = []
    for box in await page.locator(".box.connection").all():
        h2 = box.locator(".connection-head h2.reset.date")
        dep_time = await h2.evaluate("el => el.firstChild.textContent.trim()")
        dep_date = await h2.locator(".date-after").inner_text()
        dur = await box.locator(".connection-head p.reset.total strong").inner_text()
        delays = [
            (await b.inner_text()).strip()
            for b in await box.locator(".delay-bubble").all()
        ]
        legs = []
        for leg in await box.locator(".outside-of-popup").all():
            h3 = leg.locator("h3")
            if not await h3.count():
                continue
            name = (await h3.locator("span").first.inner_text()).strip()
            title = await h3.get_attribute("title") or ""
            type_ = title.split("(")[0].strip()
            legs.append({"name": name, "type": type_})

        results.append({
            "dep_time": dep_time,
            "dep_date": dep_date.strip(),
            "duration": dur.strip(),
            "delays": delays,
            "legs": legs,
        })
    return results


@router.get("/search")
async def search_connections(request: Request, from_stop: str, to_stop: str, date: str = "", time: str = "", n: int = 3):
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        core.check_rate(cf_ip)
    page = await core.browser.new_page()
    try:
        await page.goto(IDOS_URL, timeout=60000, wait_until="domcontentloaded")

        await fill_station(page, "From", "ac-from", from_stop)
        await fill_station(page, "To", "ac-to", to_stop)

        if date:
            await page.fill("#Date", date)
        if time:
            await page.fill("#Time", time)

        await page.click("button.btn-orange")
        await page.wait_for_selector(".box.connection", timeout=60000)

        results = await collect_boxes(page)

        while len(results) < n:
            prev_count = len(await page.locator(".box.connection").all())
            await page.click(".pagingNext")
            await page.wait_for_function(
                f"document.querySelectorAll('.box.connection').length !== {prev_count}",
                timeout=15000,
            )
            results.extend(await collect_boxes(page))

        return {"from": from_stop, "to": to_stop, "connections": results[:n]}
    finally:
        await page.close()
