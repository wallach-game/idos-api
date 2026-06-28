import re
import httpx
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import Response
import app as core
import peers
import proxies

DATE_RE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")

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
async def search_connections(request: Request, from_stop: str, to_stop: str, date: str = "", time: str = "", n: int = Query(default=3, ge=1, le=20)):
    hops = int(request.headers.get("x-hops", "0"))
    if peer := peers.next_peer(hops):
        fwd_headers = {"x-hops": str(hops + 1)}
        if cf := request.headers.get("CF-Connecting-IP"):
            fwd_headers["CF-Connecting-IP"] = cf
        try:
            async with httpx.AsyncClient(timeout=65) as client:
                resp = await client.get(
                    f"{peer}/api/search",
                    params=request.query_params,
                    headers=fwd_headers,
                )
            return Response(content=resp.content, media_type="application/json", status_code=resp.status_code)
        except Exception:
            pass  # peer unreachable, fall through to handle locally

    if date and not DATE_RE.match(date):
        raise HTTPException(status_code=422, detail="Invalid date format, expected DD.MM.YYYY")
    if time and not TIME_RE.match(time):
        raise HTTPException(status_code=422, detail="Invalid time format, expected HH:MM")
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        await core.check_rate(cf_ip)
    await core.acquire(cf_ip)
    await proxies.ensure_loaded()
    last_err: Exception | None = None
    try:
        for attempt in range(proxies.MAX_TRIES + 1 if proxies.ENABLED else 1):
            proxy = proxies.next_proxy() if attempt < proxies.MAX_TRIES else None
            ctx = await core.browser.new_context(**({"proxy": {"server": proxy}} if proxy else {}))
            page = await ctx.new_page()
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
            except Exception as e:
                last_err = e
            finally:
                await page.close()
                await ctx.close()
        raise last_err or HTTPException(status_code=500, detail="Scraping failed")
    finally:
        core.release(cf_ip)
