from playwright.async_api import async_playwright

_COOKIE_NAME = "rs_session"


async def get_session_cookie(retailer: str = "homedepot") -> str:
    url = f"https://www.rebelsavings.com/{retailer}/"
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(url, wait_until="networkidle")
        cookies = await context.cookies()
        await browser.close()
    for cookie in cookies:
        if cookie["name"] == _COOKIE_NAME:
            return cookie["value"]
    raise RuntimeError(
        f"rs_session cookie not set after loading {url!r}. "
        "The challenge handshake may have changed."
    )
