from playwright.async_api import async_playwright


_COOKIE_NAME = "rs_session"


async def get_session_cookie(retailer: str = "homedepot") -> str:
    url = f"https://www.rebelsavings.com/{retailer}/"
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        cookies = await context.cookies()
        await browser.close()
    for cookie in cookies:
        if cookie["name"] == _COOKIE_NAME:
            return cookie["value"]
    raise RuntimeError(
        f"rs_session cookie not set after loading {url!r}. "
        "The challenge handshake may have changed."
    )
